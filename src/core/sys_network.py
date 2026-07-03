"""Cross-platform utility for querying current connected WiFi SSID."""

import sys
import subprocess
from typing import Optional
from loguru import logger

def query_current_ssid() -> Optional[str]:
    """Return the SSID of the currently connected WiFi network, or None."""
    try:
        if sys.platform == "win32":
            # On Windows, we import the native wlanapi helper to avoid subprocess overhead.
            # We lazy import it to avoid circular dependencies or loading wlanapi on non-Windows.
            from src.core.connection_monitor_win import query_current_ssid_win
            return query_current_ssid_win()

        elif sys.platform == "darwin":
            # On macOS, use the private framework airport utility
            cmd = ["/System/Library/PrivateFrameworks/Apple80211.framework/Resources/airport", "-I"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.strip().startswith("SSID:"):
                        return line.split(":", 1)[1].strip()
            return None

        elif sys.platform.startswith("linux"):
            # On Linux, try nmcli first (very reliable, avoids localized output)
            cmd = ["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"]
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        if line.startswith("yes:"):
                            ssid = line.split(":", 1)[1].strip()
                            # nmcli might output empty strings for hidden networks, ignore them
                            if ssid:
                                return ssid
            except FileNotFoundError:
                pass

            # Fallback to iwgetid
            cmd2 = ["iwgetid", "-r"]
            try:
                result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=2)
                if result2.returncode == 0 and result2.stdout.strip():
                    return result2.stdout.strip()
            except FileNotFoundError:
                pass
            return None

    except Exception as e:
        logger.debug("Failed to query SSID on {platform}: {e}", platform=sys.platform, e=e)
        return None
