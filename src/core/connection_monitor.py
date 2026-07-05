"""Event-driven WiFi connection monitor using WlanRegisterNotification."""

import ctypes
import queue
import threading
from ctypes import POINTER, Structure, CFUNCTYPE, byref, cast, wintypes
from typing import Callable, Optional

from loguru import logger

# ── wlanapi constants ────────────────────────────────────────────

WLAN_NOTIFICATION_SOURCE_ACM = 0x00000008
ERROR_SUCCESS = 0x00000000

wlan_notification_acm_connection_complete = 16
wlan_notification_acm_disconnected = 5

wlan_intf_opcode_current_connection = 7
wlan_interface_state_connected = 1

DOT11_SSID_MAX_LENGTH = 32

# ── ctypes structures ────────────────────────────────────────────

class DOT11_SSID(Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", ctypes.c_ubyte * DOT11_SSID_MAX_LENGTH),
    ]


class WLAN_CONNECTION_NOTIFICATION_DATA(Structure):
    _fields_ = [
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", wintypes.WCHAR * 256),
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", wintypes.DWORD),
        ("bSecurityEnabled", wintypes.BOOL),
        ("wlanReasonCode", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("strProfileXml", wintypes.WCHAR * 1),
    ]


class WLAN_NOTIFICATION_DATA(Structure):
    _fields_ = [
        ("notificationSource", wintypes.DWORD),
        ("dwNotificationCode", wintypes.DWORD),
        ("guidInterface", wintypes.BYTE * 16),
        ("dwDataSize", wintypes.DWORD),
        ("pData", wintypes.LPVOID),
    ]


PWLAN_NOTIFICATION_DATA = POINTER(WLAN_NOTIFICATION_DATA)


class GUID(Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


class WLAN_INTERFACE_INFO(Structure):
    _fields_ = [
        ("InterfaceGuid", GUID),
        ("strInterfaceDescription", wintypes.WCHAR * 256),
        ("isState", wintypes.DWORD),
    ]


class WLAN_INTERFACE_INFO_LIST(Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1),
    ]


PWLAN_INTERFACE_INFO_LIST = POINTER(WLAN_INTERFACE_INFO_LIST)


class WLAN_ASSOCIATION_ATTRIBUTES(Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", wintypes.DWORD),
        ("dot11Bssid", wintypes.BYTE * 6),
        ("dot11PhyType", wintypes.DWORD),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("bInReset", wintypes.BOOL),
    ]


class WLAN_SECURITY_ATTRIBUTES(Structure):
    _fields_ = [
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
        ("dot11AuthAlgorithm", wintypes.DWORD),
        ("dot11CipherAlgorithm", wintypes.DWORD),
    ]


class WLAN_CONNECTION_ATTRIBUTES(Structure):
    _fields_ = [
        ("isState", wintypes.DWORD),
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", wintypes.WCHAR * 256),
        ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
        ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES),
    ]


PWLAN_CONNECTION_ATTRIBUTES = POINTER(WLAN_CONNECTION_ATTRIBUTES)


# ── callback type ────────────────────────────────────────────────

WLAN_NOTIFICATION_CALLBACK = CFUNCTYPE(None, PWLAN_NOTIFICATION_DATA, wintypes.LPVOID)

# ── wlanapi function bindings ────────────────────────────────────

_wlanapi = ctypes.windll.wlanapi

_WlanOpenHandle = _wlanapi.WlanOpenHandle
_WlanOpenHandle.argtypes = [
    wintypes.DWORD,       # dwClientVersion
    wintypes.LPVOID,      # pReserved
    POINTER(wintypes.DWORD),  # pdwNegotiatedVersion
    POINTER(wintypes.LPVOID), # phClientHandle
]
_WlanOpenHandle.restype = wintypes.DWORD

_WlanRegisterNotification = _wlanapi.WlanRegisterNotification
_WlanRegisterNotification.argtypes = [
    wintypes.LPVOID,      # hClientHandle
    wintypes.DWORD,       # dwNotifSource
    wintypes.BOOL,        # bIgnoreDuplicate
    wintypes.LPVOID,      # funcCallback (c_void_p to accept None)
    wintypes.LPVOID,      # pCallbackContext
    wintypes.LPVOID,      # pReserved
    POINTER(wintypes.DWORD),  # pdwPrevNotifSource
]
_WlanRegisterNotification.restype = wintypes.DWORD

_WlanCloseHandle = _wlanapi.WlanCloseHandle
_WlanCloseHandle.argtypes = [
    wintypes.LPVOID,      # hClientHandle
    wintypes.LPVOID,      # pReserved
]
_WlanCloseHandle.restype = wintypes.DWORD

_WlanEnumInterfaces = _wlanapi.WlanEnumInterfaces
_WlanEnumInterfaces.argtypes = [
    wintypes.LPVOID,      # hClientHandle
    wintypes.LPVOID,      # pReserved
    POINTER(PWLAN_INTERFACE_INFO_LIST),  # ppInterfaceList
]
_WlanEnumInterfaces.restype = wintypes.DWORD

_WlanQueryInterface = _wlanapi.WlanQueryInterface
_WlanQueryInterface.argtypes = [
    wintypes.LPVOID,      # hClientHandle
    POINTER(GUID),        # pInterfaceGuid
    wintypes.DWORD,       # OpCode
    wintypes.LPVOID,      # pReserved (must be NULL)
    POINTER(wintypes.DWORD),  # pdwDataSize
    POINTER(wintypes.LPVOID), # ppData
    POINTER(wintypes.LPVOID), # pOpCodeOwner (must be NULL)
]
_WlanQueryInterface.restype = wintypes.DWORD

_WlanFreeMemory = _wlanapi.WlanFreeMemory
_WlanFreeMemory.argtypes = [
    wintypes.LPVOID,      # pMemory
]
_WlanFreeMemory.restype = wintypes.DWORD


def query_current_ssid() -> Optional[tuple[str, bool]]:
    """Query the SSID and security status of the currently connected WiFi interface.

    Returns (ssid, secure) or None if not connected or on error.
    """
    version = wintypes.DWORD()
    handle = wintypes.LPVOID()

    ret = _WlanOpenHandle(2, None, byref(version), byref(handle))
    if ret != ERROR_SUCCESS:
        logger.warning("WlanOpenHandle failed: {ret}", ret=ret)
        return None

    try:
        iface_list = PWLAN_INTERFACE_INFO_LIST()
        ret = _WlanEnumInterfaces(handle, None, byref(iface_list))
        if ret != ERROR_SUCCESS:
            logger.warning("WlanEnumInterfaces failed: {ret}", ret=ret)
            return None

        count = iface_list.contents.dwNumberOfItems
        info_array = cast(
            byref(iface_list.contents.InterfaceInfo),
            POINTER(WLAN_INTERFACE_INFO),
        )

        for i in range(count):
            info = info_array[i]
            if info.isState == wlan_interface_state_connected:
                guid = info.InterfaceGuid
                buf_size = wintypes.DWORD()
                buf_ptr = wintypes.LPVOID()
                ret = _WlanQueryInterface(
                    handle,
                    byref(guid),
                    wlan_intf_opcode_current_connection,
                    None,
                    byref(buf_size),
                    byref(buf_ptr),
                    None,
                )
                if ret != ERROR_SUCCESS:
                    continue

                try:
                    conn_attrs = cast(buf_ptr, PWLAN_CONNECTION_ATTRIBUTES).contents
                    ssid_len = conn_attrs.wlanAssociationAttributes.dot11Ssid.uSSIDLength
                    if 0 < ssid_len <= DOT11_SSID_MAX_LENGTH:
                        ssid_bytes = bytes(
                            conn_attrs.wlanAssociationAttributes.dot11Ssid.ucSSID[:ssid_len]
                        )
                        secure = bool(conn_attrs.wlanSecurityAttributes.bSecurityEnabled)
                        return (ssid_bytes.decode("utf-8", errors="replace"), secure)
                finally:
                    _WlanFreeMemory(buf_ptr)
    finally:
        _WlanCloseHandle(handle, None)

    return None


class ConnectionMonitor:
    """Monitor WiFi connection state via WlanRegisterNotification (event-driven).

    Receives event-driven notifications when the system connects to or
    disconnects from a WiFi network. Uses Windows wlanapi under the hood.
    """

    def __init__(self) -> None:
        self._handle: Optional[int] = None
        self._callback_ref: Optional[WLAN_NOTIFICATION_CALLBACK] = None
        self._running = threading.Event()
        self._queue: queue.Queue = queue.Queue()
        self._current_ssid: Optional[str] = None
        self._current_secure: bool = False
        self._on_ssid_changed: Optional[Callable[[Optional[str], Optional[str], bool], None]] = None

    # ── public API ───────────────────────────────────────────────

    def start(self) -> None:
        """Open wlanapi handle and register for ACM notifications."""
        if self._running.is_set():
            return

        version = wintypes.DWORD()
        handle = wintypes.LPVOID()

        ret = _WlanOpenHandle(2, None, byref(version), byref(handle))
        if ret != ERROR_SUCCESS:
            logger.error("WlanOpenHandle failed: {ret}", ret=ret)
            raise OSError(f"WlanOpenHandle returned {ret}")

        self._handle = handle
        logger.debug("WlanOpenHandle succeeded, negotiated v{ver}", ver=version.value)

        # Keep a strong reference to the callback so GC does not collect it.
        self._callback_ref = WLAN_NOTIFICATION_CALLBACK(self._notification_callback)

        prev = wintypes.DWORD()
        ret = _WlanRegisterNotification(
            self._handle,
            WLAN_NOTIFICATION_SOURCE_ACM,
            True,   # bIgnoreDuplicate
            self._callback_ref,
            None,   # pCallbackContext
            None,   # pReserved
            byref(prev),
        )
        if ret != ERROR_SUCCESS:
            _WlanCloseHandle(self._handle, None)
            self._handle = None
            self._callback_ref = None
            logger.error("WlanRegisterNotification failed: {ret}", ret=ret)
            raise OSError(f"WlanRegisterNotification returned {ret}")

        self._running.set()
        logger.info("ConnectionMonitor started (WlanRegisterNotification)")

    def stop(self) -> None:
        """Close the wlanapi handle (auto-unregisters notifications)."""
        self._running.clear()

        if self._handle:
            _WlanCloseHandle(self._handle, None)
            self._handle = None
            logger.debug("ConnectionMonitor: WlanCloseHandle done")

        self._callback_ref = None  # release the callback reference

        # Drain any remaining events.
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    @property
    def current_ssid(self) -> Optional[str]:
        return self._current_ssid

    @property
    def current_secure(self) -> bool:
        return self._current_secure

    def set_initial_ssid(self, ssid: Optional[str], secure: bool = False) -> None:
        """Set the initial SSID without triggering callbacks."""
        self._current_ssid = ssid
        self._current_secure = secure

    def on_ssid_changed(self, callback: Callable[[Optional[str], Optional[str], bool], None]) -> None:
        """Register a callback invoked when the SSID changes.

        The callback receives (old_ssid, new_ssid, secure).
        """
        self._on_ssid_changed = callback

    def poll(self, timeout: float = 1.0) -> Optional[str]:
        """Process one pending WiFi event from the queue.

        Blocks up to *timeout* seconds waiting for an event. Returns
        the new SSID if a connection change occurred, otherwise None.
        The registered on_ssid_changed callback (if any) is invoked
        before returning.
        """
        try:
            event = self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

        event_type = event.get("type")

        if event_type == "connected":
            new_ssid = event.get("ssid")
            secure = event.get("secure", False)
            old_ssid = self._current_ssid
            if new_ssid != old_ssid:
                self._current_ssid = new_ssid
                self._current_secure = secure
                logger.info(
                    "SSID changed: {old} -> {new} (secure: {sec})",
                    old=old_ssid or "(none)",
                    new=new_ssid or "(none)",
                    sec=secure,
                )
                if self._on_ssid_changed:
                    self._on_ssid_changed(old_ssid, new_ssid, secure)
                return new_ssid

        elif event_type == "disconnected":
            old_ssid = self._current_ssid
            if old_ssid is not None:
                self._current_ssid = None
                self._current_secure = False
                logger.info("WiFi disconnected (was: {ssid})", ssid=old_ssid)
                if self._on_ssid_changed:
                    self._on_ssid_changed(old_ssid, None, False)
            return None

        return None

    # ── internal ─────────────────────────────────────────────────

    def _notification_callback(self, notification_data: PWLAN_NOTIFICATION_DATA, context) -> None:
        """Called by Windows on a thread-pool thread. Must not block."""
        if not self._running.is_set():
            return

        source = notification_data.contents.notificationSource
        code = notification_data.contents.dwNotificationCode

        if source == WLAN_NOTIFICATION_SOURCE_ACM:
            if code == wlan_notification_acm_connection_complete:
                self._handle_connected(notification_data.contents)
            elif code == wlan_notification_acm_disconnected:
                self._queue.put({"type": "disconnected"})

    def _handle_connected(self, data: WLAN_NOTIFICATION_DATA) -> None:
        """Extract SSID from connection notification data and push to queue."""
        if not data.pData or data.dwDataSize < ctypes.sizeof(WLAN_CONNECTION_NOTIFICATION_DATA):
            return

        conn_data = cast(data.pData, POINTER(WLAN_CONNECTION_NOTIFICATION_DATA)).contents
        ssid_len = conn_data.dot11Ssid.uSSIDLength

        if ssid_len == 0 or ssid_len > DOT11_SSID_MAX_LENGTH:
            return

        ssid_bytes = bytes(conn_data.dot11Ssid.ucSSID[:ssid_len])
        ssid = ssid_bytes.decode("utf-8", errors="replace")

        if ssid:
            secure = bool(conn_data.bSecurityEnabled)
            self._queue.put({"type": "connected", "ssid": ssid, "secure": secure})
