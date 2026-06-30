r"""Windows autostart via HKCU\Software\Microsoft\Windows\CurrentVersion\Run."""

import sys
import winreg
from pathlib import Path


class AutostartManager:
    """Manage the 'Run' registry key for automatic startup."""

    _RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

    def __init__(self, app_name: str) -> None:
        self._app_name = app_name
        self._exe_path = self._resolve_exe_path()

    # ── public API ───────────────────────────────────────────────

    def register(self) -> bool:
        """Register the application to run at user login."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, self._app_name, 0, winreg.REG_SZ, self._exe_path)
            return True
        except OSError:
            return False

    def remove(self) -> bool:
        """Remove the autostart registry entry."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, self._app_name)
            return True
        except OSError:
            return False

    def is_registered(self) -> bool:
        """Check if the autostart entry exists and points to this executable."""
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self._RUN_KEY, 0, winreg.KEY_READ) as key:
                value, _ = winreg.QueryValueEx(key, self._app_name)
                return value == self._exe_path
        except OSError:
            return False

    @property
    def exe_path(self) -> str:
        return self._exe_path

    # ── internal ─────────────────────────────────────────────────

    @staticmethod
    def _resolve_exe_path() -> str:
        """Return the current executable path.

        Supports PyInstaller frozen exe and plain python script.
        """
        if getattr(sys, "frozen", False):
            return sys.executable
        # Running as script — use the venv pythonw.exe if available.
        exe = Path(sys.executable)
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
        return str(exe)
