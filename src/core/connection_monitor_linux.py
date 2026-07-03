"""Linux WiFi connection monitor using DBus and jeepney for zero-energy events."""

import threading
import queue
import time
from typing import Callable, Optional
from loguru import logger

from src.core.sys_network import query_current_ssid


class LinuxConnectionMonitor:
    """Monitor WiFi connection state via NetworkManager D-Bus signals (event-driven)."""

    def __init__(self) -> None:
        self._running = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._current_ssid: Optional[str] = None
        self._on_ssid_changed: Optional[Callable[[Optional[str], Optional[str]], None]] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._running.is_set():
            return

        self._running.set()
        self._thread = threading.Thread(target=self._dbus_loop, daemon=True)
        self._thread.start()
        logger.info("ConnectionMonitor started (Linux D-Bus via jeepney)")

    def stop(self) -> None:
        self._running.clear()
        
        # We need to wake up the blocked dbus loop. Since jeepney recv is blocking,
        # it might take up to timeout (5s) to exit.
        if self._thread:
            self._thread.join(timeout=6.0)

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

    def _dbus_loop(self) -> None:
        try:
            from jeepney.io.blocking import open_dbus_connection, Proxy
            from jeepney.bus_messages import MatchRule, message_bus
        except ImportError:
            logger.error("jeepney is not installed. Linux connection monitor will not work.")
            return

        try:
            conn = open_dbus_connection(bus='SYSTEM')
        except Exception as e:
            logger.error(f"Failed to connect to SYSTEM bus: {e}")
            return

        # Listen to PropertiesChanged on NetworkManager
        match_rule = MatchRule(
            type='signal',
            interface='org.freedesktop.NetworkManager',
            member='PropertiesChanged',
            path='/org/freedesktop/NetworkManager'
        )

        try:
            bus_proxy = Proxy(message_bus, conn)
            bus_proxy.AddMatch(match_rule)
        except Exception as e:
            logger.error(f"Failed to AddMatch for DBus signals: {e}")
            conn.close()
            return

        # Also match StateChanged just in case
        match_rule_state = MatchRule(
            type='signal',
            interface='org.freedesktop.NetworkManager',
            member='StateChanged',
            path='/org/freedesktop/NetworkManager'
        )
        try:
            bus_proxy.AddMatch(match_rule_state)
        except Exception:
            pass

        with conn.filter(match_rule, bufsize=20) as q_prop, \
             conn.filter(match_rule_state, bufsize=20) as q_state:
            while self._running.is_set():
                received = False
                try:
                    # Timeout determines how long we block before checking _running flag
                    _ = conn.recv_until_filtered(q_prop, timeout=5.0)
                    received = True
                except TimeoutError:
                    pass
                
                if not received:
                    try:
                        _ = conn.recv_until_filtered(q_state, timeout=0.1)
                        received = True
                    except TimeoutError:
                        pass
                
                if received and self._running.is_set():
                    # Let the system settle, then query SSID
                    time.sleep(1.0)
                    new_ssid = query_current_ssid()
                    if new_ssid != self._current_ssid:
                        self._queue.put({"type": "changed", "ssid": new_ssid})

        try:
            conn.close()
        except Exception:
            pass
