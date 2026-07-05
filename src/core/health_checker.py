"""Check internet connectivity by probing a known HTTP URL."""

from typing import Callable, Optional

from loguru import logger

from .portal_detector import concurrent_detect_captive_portal, PortalStatus


class HealthChecker:
    """Run a one-shot connectivity probe and fire a callback if captive."""

    def __init__(
        self,
        probe_urls: Optional[list[str]] = None,
    ) -> None:
        self._probe_urls = probe_urls or [
            "http://captive.apple.com", 
            "http://www.msftconnecttest.com/connecttest.txt",
            "http://gstatic.com/generate_204"
        ]
        self._on_portal_detected: Optional[Callable[[str], None]] = None

    def reset_probe_index(self) -> None:
        """Reset the probe index (legacy, kept for compatibility)."""
        pass

    def on_portal_detected(self, callback: Callable[[str], None]) -> None:
        self._on_portal_detected = callback

    def check(self) -> tuple[PortalStatus, Optional[str]]:
        """Probe connectivity.

        Returns
        -------
        tuple[PortalStatus, Optional[str]]
            The status and the captive portal URL if captive.
        """
        status, portal_url = concurrent_detect_captive_portal(self._probe_urls)

        if status == PortalStatus.PORTAL and portal_url is not None:
            logger.warning("Captive portal detected at {url}", url=portal_url)
            if self._on_portal_detected:
                self._on_portal_detected(portal_url)

        if status == PortalStatus.ERROR:
            logger.debug("All concurrent probes resulted in ERROR")

        return status, portal_url
