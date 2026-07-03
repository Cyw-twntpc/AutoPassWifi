r"""Cross-platform autostart manager."""

import sys
import os
from pathlib import Path
from loguru import logger


class AutostartManager:
    """Manage automatic startup across Windows, macOS, and Linux."""

    def __init__(self, app_name: str) -> None:
        self._app_name = app_name
        self._exe_path = self._resolve_exe_path()
        self._platform = sys.platform

    # ── public API ───────────────────────────────────────────────

    def register(self) -> bool:
        """Register the application to run at user login."""
        try:
            if self._platform == "win32":
                return self._register_windows()
            elif self._platform == "darwin":
                return self._register_macos()
            elif self._platform.startswith("linux"):
                return self._register_linux()
            return False
        except Exception as e:
            logger.error("Autostart register error: {e}", e=e)
            return False

    def remove(self) -> bool:
        """Remove the autostart registry/file."""
        try:
            if self._platform == "win32":
                return self._remove_windows()
            elif self._platform == "darwin":
                return self._remove_macos()
            elif self._platform.startswith("linux"):
                return self._remove_linux()
            return False
        except Exception as e:
            logger.error("Autostart remove error: {e}", e=e)
            return False

    def is_registered(self) -> bool:
        """Check if the autostart entry exists and points to this executable."""
        try:
            if self._platform == "win32":
                return self._is_registered_windows()
            elif self._platform == "darwin":
                return self._is_registered_macos()
            elif self._platform.startswith("linux"):
                return self._is_registered_linux()
            return False
        except Exception as e:
            logger.error("Autostart is_registered error: {e}", e=e)
            return False

    @property
    def exe_path(self) -> str:
        return self._exe_path

    # ── internal ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_exe_path() -> str:
        """Return the current executable path."""
        if getattr(sys, "frozen", False):
            return sys.executable
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
        return str(exe)

    # ── Windows ──────────────────────────────────────────────────

    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def _register_windows(self) -> bool:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, self._app_name, 0, winreg.REG_SZ, self._exe_path)
        return True

    def _remove_windows(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._app_name)
            return True
        except FileNotFoundError:
            return True

    def _is_registered_windows(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self._app_name)
                return value == self._exe_path
        except FileNotFoundError:
            return False

    # ── macOS ────────────────────────────────────────────────────

    @property
    def _macos_plist_path(self) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / f"com.{self._app_name}.plist"

    def _register_macos(self) -> bool:
        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{self._app_name}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{self._exe_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>"""
        self._macos_plist_path.parent.mkdir(parents=True, exist_ok=True)
        self._macos_plist_path.write_text(plist_content, encoding="utf-8")
        return True

    def _remove_macos(self) -> bool:
        if self._macos_plist_path.exists():
            self._macos_plist_path.unlink()
        return True

    def _is_registered_macos(self) -> bool:
        if not self._macos_plist_path.exists():
            return False
        content = self._macos_plist_path.read_text(encoding="utf-8")
        return self._exe_path in content

    # ── Linux ────────────────────────────────────────────────────

    @property
    def _linux_desktop_path(self) -> Path:
        return Path.home() / ".config" / "autostart" / f"{self._app_name}.desktop"

    def _register_linux(self) -> bool:
        desktop_content = f"""[Desktop Entry]
Type=Application
Exec={self._exe_path}
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
Name={self._app_name}
Comment=AutoPassWiFi background service
"""
        self._linux_desktop_path.parent.mkdir(parents=True, exist_ok=True)
        self._linux_desktop_path.write_text(desktop_content, encoding="utf-8")
        return True

    def _remove_linux(self) -> bool:
        if self._linux_desktop_path.exists():
            self._linux_desktop_path.unlink()
        return True

    def _is_registered_linux(self) -> bool:
        if not self._linux_desktop_path.exists():
            return False
        content = self._linux_desktop_path.read_text(encoding="utf-8")
        return self._exe_path in content
