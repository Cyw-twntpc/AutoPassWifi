"""Wrapper around netsh wlan commands for WiFi interface info."""

import re
import subprocess
from dataclasses import dataclass
from typing import Optional


@dataclass
class InterfaceInfo:
    """Parsed result of `netsh wlan show interfaces`."""
    name: str
    ssid: Optional[str]
    state: str  # "connected", "disconnected", etc.
    profile: Optional[str]
    signal_quality: Optional[int]


def _run_netsh(*args: str) -> str:
    """Run a netsh command and return stdout as text."""
    result = subprocess.run(
        ["netsh", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=10,
    )
    return result.stdout


def get_interfaces() -> list[InterfaceInfo]:
    """Parse `netsh wlan show interfaces` into a list of InterfaceInfo."""
    raw = _run_netsh("wlan", "show", "interfaces")
    interfaces: list[InterfaceInfo] = []
    current: dict = {}

    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^\s*(?:名稱|Name)\s*:\s*(.+)$", line)
        if m:
            if current:
                interfaces.append(_make_interface(current))
            current = {"name": m.group(1)}
            continue
        m = re.match(r"^\s*SSID\s*:\s*(.+)$", line)
        if m:
            ssid_val = m.group(1).strip()
            current["ssid"] = ssid_val if ssid_val != "" else None
            continue
        m = re.match(r"^\s*(?:狀態|State)\s*:\s*(.+)$", line)
        if m:
            current["state"] = m.group(1).strip().lower()
            continue
        m = re.match(r"^\s*(?:設定檔|Profile)\s*:\s*(.+)$", line)
        if m:
            profile_val = m.group(1).strip()
            current["profile"] = profile_val if profile_val != "" else None
            continue
        m = re.match(r"^\s*(?:訊號|Signal)\s*:\s*(\d+)%", line)
        if m:
            current["signal_quality"] = int(m.group(1))
            continue

    if current:
        interfaces.append(_make_interface(current))

    return interfaces


def _make_interface(d: dict) -> InterfaceInfo:
    return InterfaceInfo(
        name=d.get("name", ""),
        ssid=d.get("ssid"),
        state=d.get("state", "disconnected"),
        profile=d.get("profile"),
        signal_quality=d.get("signal_quality"),
    )


def get_current_ssid() -> Optional[str]:
    """Return the SSID of the first connected interface, or None."""
    connected_states = {"connected", "連線", "已連線"}
    for iface in get_interfaces():
        if iface.state and iface.state in connected_states:
            return iface.ssid
    return None
