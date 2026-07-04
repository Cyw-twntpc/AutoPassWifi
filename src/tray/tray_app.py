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

        app_dir = get_app_dir()

        # In frozen mode, point Playwright to the Chromium browser bundled
        # alongside the exe by the installer.
        if getattr(sys, "frozen", False):
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(app_dir)

        # Check Chromium directories exist and warn if missing.
        chrome_dirs = [
            app_dir / "chromium-1228",
        ]
        missing = [str(d) for d in chrome_dirs if not d.is_dir()]
        if missing:
            _show_warning(
                "Chromium Browser Not Found",
                "Chromium browser not found. Please reinstall.\n\n"
                "Missing:\n" + "\n".join(missing),
            )

        # Load or generate icons.
        self._icon_active = self._load_icon("icon.ico") or self._draw_default_icon(active=True)
        self._icon_paused = self._load_icon("icon_disabled.ico") or self._draw_default_icon(active=False)

        # Build pystray menu.
        self._menu = pystray.Menu(
            pystray.MenuItem("Enable", self._on_start, enabled=lambda item: not self._running),
            pystray.MenuItem("Pause", self._on_stop, enabled=lambda item: self._running),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Check for Updates", self._on_update),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._on_exit),
        )

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

    def _on_update(self) -> None:
        """Trigger an immediate update check in the background."""
        from src.utils.updater import updater
        # Start a quick thread so it doesn't block the UI
        threading.Thread(target=updater.check_and_install_update, daemon=True).start()

    def _on_exit(self) -> None:
        """Exit — stop engine and release resources."""
        self._stop_engine()
        if self._icon:
            self._icon.stop()

    # ── engine lifecycle ─────────────────────────────────────────

    def _start_engine(self) -> None:
        """Start the Engine in a background daemon thread."""
        if self._running:
            return

        def _run_engine() -> None:
            pw_ctx = sync_playwright()
            try:
                pw = pw_ctx.start()
                engine = Engine(self._config, playwright_instance=pw)
                self._engine = engine
                engine.run()
            except Exception as exc:
                logger.error("Engine error: {exc}", exc=exc)
            finally:
                try:
                    pw_ctx.__exit__(None, None, None)
                except Exception:
                    pass
                self._running = False
                self._engine = None
                self._update_icon()

        self._running = True
        self._thread = threading.Thread(target=_run_engine, daemon=False)
        self._thread.start()

    def _stop_engine(self) -> None:
        """Signal the Engine to stop."""
        if self._engine and self._running:
            try:
                self._engine.stop()
            except Exception as exc:
                logger.warning("Engine stop error: {exc}", exc=exc)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)

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
