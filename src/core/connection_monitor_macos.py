"""macOS WiFi connection monitor using Swift background process for zero-energy events."""

import threading
import queue
import time
import subprocess
from typing import Callable, Optional
from loguru import logger

from src.core.sys_network import query_current_ssid

# Minimal Swift script to listen for network state changes.
# It uses SCDynamicStore to subscribe to network interface changes.
_SWIFT_LISTENER = """
import Foundation
import SystemConfiguration

let store = SCDynamicStoreCreate(nil, "AutoPassWiFiMonitor" as CFString, { (store, changedKeys, context) in
    print("WIFI_CHANGED")
    fflush(stdout)
}, nil)

if let store = store {
    let keys = ["State:/Network/Interface/.+/IPv4", "State:/Network/Interface/.+/AirPort"] as CFArray
    SCDynamicStoreSetNotificationKeys(store, nil, keys)

    let runLoopSource = SCDynamicStoreCreateRunLoopSource(nil, store, 0)
    CFRunLoopAddSource(CFRunLoopGetCurrent(), runLoopSource, .defaultMode)
    CFRunLoopRun()
}
"""


class MacConnectionMonitor:
    """Monitor WiFi connection state via macOS Native APIs via Swift (event-driven)."""

    def __init__(self) -> None:
        self._running = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._current_ssid: Optional[str] = None
        self._on_ssid_changed: Optional[Callable[[Optional[str], Optional[str]], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._proc: Optional[subprocess.Popen] = None

    def start(self) -> None:
        if self._running.is_set():
            return

        self._running.set()
        self._thread = threading.Thread(target=self._swift_loop, daemon=True)
        self._thread.start()
        logger.info("ConnectionMonitor started (macOS Swift Helper)")

    def stop(self) -> None:
        self._running.clear()
        
        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
            
        if self._thread:
            self._thread.join(timeout=2.0)

        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    @property
    def current_ssid(self) -> Optional[str]:
        return self._current_ssid

    def set_initial_ssid(self, ssid: Optional[str]) -> None:
        self._current_ssid = ssid

    def on_ssid_changed(self, callback: Callable[[Optional[str], Optional[str]], None]) -> None:
        self._on_ssid_changed = callback

    def poll(self, timeout: float = 1.0) -> Optional[str]:
        try:
            event = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        event_type = event.get("type")
        if event_type == "changed":
            new_ssid = event.get("ssid")
            old_ssid = self._current_ssid
            if new_ssid != old_ssid:
                self._current_ssid = new_ssid
                logger.info(
                    "SSID changed: {old} -> {new}",
                    old=old_ssid or "(none)",
                    new=new_ssid or "(none)",
                )
                if self._on_ssid_changed:
                    self._on_ssid_changed(old_ssid, new_ssid)
                return new_ssid

        return None

    def _swift_loop(self) -> None:
        try:
            self._proc = subprocess.Popen(
                ["swift", "-e", _SWIFT_LISTENER],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
        except FileNotFoundError:
            logger.error("swift compiler not found. Ensure Xcode Command Line Tools are installed.")
            return
        except Exception as e:
            logger.error(f"Failed to start Swift monitor: {e}")
            return

        while self._running.is_set():
            try:
                # readline will block until Swift prints something
                line = self._proc.stdout.readline()
                if not line:
                    break
                if "WIFI_CHANGED" in line:
                    # Let the system settle, then query SSID
                    time.sleep(1.0)
                    new_ssid = query_current_ssid()
                    if new_ssid != self._current_ssid:
                        self._queue.put({"type": "changed", "ssid": new_ssid})
            except Exception as e:
                logger.debug(f"Error reading from Swift monitor: {e}")
                break

        if self._proc:
            try:
                self._proc.terminate()
            except Exception:
                pass
