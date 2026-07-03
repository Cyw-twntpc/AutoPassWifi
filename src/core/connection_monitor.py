"""WiFi connection monitor factory."""

import sys

from src.core.sys_network import query_current_ssid

if sys.platform == "win32":
    from src.core.connection_monitor_win import WindowsConnectionMonitor as ConnectionMonitor
elif sys.platform == "darwin":
    from src.core.connection_monitor_macos import MacConnectionMonitor as ConnectionMonitor
elif sys.platform.startswith("linux"):
    from src.core.connection_monitor_linux import LinuxConnectionMonitor as ConnectionMonitor
else:
    # Fallback dummy for unknown platforms
    class ConnectionMonitor:
        def start(self): pass
        def stop(self): pass
        def set_initial_ssid(self, ssid): pass
        def on_ssid_changed(self, cb): pass
        def poll(self, timeout=1.0): return None
        @property
        def current_ssid(self): return None

__all__ = ["ConnectionMonitor", "query_current_ssid"]
