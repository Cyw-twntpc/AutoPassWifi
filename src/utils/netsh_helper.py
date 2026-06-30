"""Legacy compatibility shim — delegates to WlanAPI-based SSID query."""

from typing import Optional

from src.core.connection_monitor import query_current_ssid


def get_current_ssid() -> Optional[str]:
    """Return the SSID of the first connected WiFi interface, or None.

    Uses WlanQueryInterface (WlanAPI), locale-independent.
    Replaced the original netsh-based implementation.
    """
    return query_current_ssid()
