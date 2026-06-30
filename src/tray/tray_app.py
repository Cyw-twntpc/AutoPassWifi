"""System tray application with pystray — manages Engine lifecycle in background thread."""

import os
import sys
import threading
from pathlib import Path
from typing import Optional

import pystray
from loguru import logger
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

from src.main import Engine
from src.utils.autostart import AutostartManager
from src.utils.config import AppConfig
from src.utils.paths import get_app_dir

try:
    import tkinter.messagebox as msgbox
except ImportError:
    msgbox = None


def _show_warning(title: str, message: str) -> None:
    """Show a warning dialog or fall back to log if tkinter unavailable."""
    logger.warning("{title}: {msg}", title=title, msg=message)
    if msgbox:
        try:
            msgbox.showwarning(title, message)
        except Exception:
            pass


class TrayApp:
    """System tray icon that controls the autopasswifi Engine in background.

    Single Playwright instance is reused across Engine restarts.
    """

    _ICON_SIZE = 64

    def __init__(self) -> None:
        self._config = AppConfig.load()
        self._running = False
        self._engine: Optional[Engine] = None
        self._thread: Optional[threading.Thread] = None
        self._playwright: Optional[sync_playwright] = None
        self._pw_instance: Optional[sync_playwright] = None
        self._autostart = AutostartManager("AutoPassWiFi")

        # In frozen mode, point Playwright to the Chromium browser bundled
        # alongside the exe by the installer.
        if getattr(sys, "frozen", False):
            app_dir = get_app_dir()
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(app_dir)

            # Check Chromium exists and warn if missing.
            chrome_dir = app_dir / "chromium-1228"
            if not chrome_dir.is_dir():
                _show_warning(
                    "Chromium 瀏覽器未找到",
                    "無法找到 Chromium 瀏覽器，請重新安裝程式。\n\n"
                    f"預期位置：{chrome_dir}",
                )

        # Load or generate icons.
        self._icon_active = self._load_icon("icon.ico") or self._draw_default_icon(active=True)
        self._icon_paused = self._load_icon("icon_disabled.ico") or self._draw_default_icon(active=False)

        # Build pystray menu.
        self._menu = pystray.Menu(
            pystray.MenuItem("啟用", self._on_start, enabled=lambda: not self._running),
            pystray.MenuItem("暫停", self._on_stop, enabled=lambda: self._running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("離開", self._on_exit),
        )

        # Ensure autostart is registered (installer typically does this).
        if not self._autostart.is_registered():
            logger.info("Registering autostart entry")
            self._autostart.register()

    # ── public API ───────────────────────────────────────────────

    def run(self) -> None:
        """Start the engine and enter the tray event loop (blocks)."""
        self._start_engine()

        icon = pystray.Icon("autopasswifi", self._icon_active, "AutoPassWiFi", self._menu)
        self._icon = icon
        icon.run()

    # ── callbacks ────────────────────────────────────────────────

    def _on_start(self) -> None:
        """Enable — start the engine."""
        if not self._running:
            self._start_engine()
            self._update_icon()

    def _on_stop(self) -> None:
        """Pause — stop the engine."""
        if self._running:
            self._stop_engine()
            self._update_icon()

    def _on_exit(self) -> None:
        """Exit — stop engine and release resources."""
        self._stop_engine()
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            if self._pw_instance:
                try:
                    self._pw_instance.__exit__(None, None, None)
                except Exception:
                    pass
        if self._icon:
            self._icon.stop()

    # ── engine lifecycle ─────────────────────────────────────────

    def _start_engine(self) -> None:
        """Start the Engine in a background daemon thread."""
        if self._running:
            return

        # Ensure Playwright is started once.
        if not self._playwright:
            pw_instance = sync_playwright()
            try:
                self._playwright = pw_instance.start()
                self._pw_instance = pw_instance  # keep for cleanup
            except Exception:
                pw_instance.__exit__(None, None, None)
                raise

        try:
            engine = Engine(self._config, playwright_instance=self._playwright)
            self._engine = engine
        except Exception as exc:
            logger.error("Failed to create Engine: {exc}", exc=exc)
            return

        def _run_engine() -> None:
            try:
                engine.run()
            except Exception as exc:
                logger.error("Engine crashed: {exc}", exc=exc)
            finally:
                self._running = False
                self._engine = None
                self._update_icon()

        self._running = True
        self._thread = threading.Thread(target=_run_engine, daemon=True)
        self._thread.start()

    def _stop_engine(self) -> None:
        """Signal the Engine to stop."""
        if self._engine and self._running:
            try:
                self._engine.stop()
            except Exception as exc:
                logger.warning("Engine stop error: {exc}", exc=exc)
        self._engine = None
        self._running = False
        self._thread = None

    # ── icon management ──────────────────────────────────────────

    def _update_icon(self) -> None:
        """Swap icon based on running state."""
        if not self._icon:
            return
        self._icon.icon = self._icon_active if self._running else self._icon_paused

    def _load_icon(self, name: str) -> Optional[Image.Image]:
        """Try loading an icon file from the tray package directory."""
        # Frozen: icons are at sys._MEIPASS/tray/ (via --add-data).
        # Dev: icons are at src/tray/.
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys._MEIPASS) / "tray" / name)
        candidates.append(Path(__file__).parent / name)
        for ico_path in candidates:
            if ico_path.exists():
                try:
                    return Image.open(ico_path)
                except Exception:
                    pass
        return None

    @staticmethod
    def _draw_default_icon(active: bool = True) -> Image.Image:
        """Draw a simple WiFi icon using Pillow as fallback."""
        img = Image.new("RGBA", (TrayApp._ICON_SIZE, TrayApp._ICON_SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        cx, cy = TrayApp._ICON_SIZE // 2, TrayApp._ICON_SIZE // 2 + 4
        color = (76, 175, 80) if active else (180, 180, 180)

        # Draw three curved arcs to represent WiFi signal.
        for r in (8, 14, 20):
            bbox = [cx - r, cy - r, cx + r, cy + r]
            draw.arc(bbox, start=-220, end=-320, fill=color, width=3)

        # Dot at bottom.
        dot_r = 2
        draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill=color)

        return img
