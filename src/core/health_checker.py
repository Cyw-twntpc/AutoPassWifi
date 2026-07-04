"""Check internet connectivity by probing a known HTTP URL."""

from typing import Callable, Optional

from loguru import logger

from .portal_detector import detect_captive_portal, PortalStatus


class HealthChecker:
    """Run a one-shot connectivity probe and fire a callback if captive."""

    def __init__(
        self,
        probe_urls: Optional[list[str]] = None,
    ) -> None:
        self._probe_urls = probe_urls or ["http://captive.apple.com", "http://www.msftconnecttest.com/connecttest.txt"]
        self._on_portal_detected: Optional[Callable[[str], None]] = None
        self._working_index = 0

    def reset_probe_index(self) -> None:
        """Reset the probe index to start from the primary URL."""
        self._working_index = 0

    def on_portal_detected(self, callback: Callable[[str], None]) -> None:
        self._on_portal_detected = callback

    def check(self) -> tuple[PortalStatus, Optional[str]]:
        """Probe connectivity.

        Returns
        -------
        tuple[PortalStatus, Optional[str]]
            The status and the captive portal URL if captive.
        """
        for i in range(self._working_index, len(self._probe_urls)):
            url = self._probe_urls[i]
            status, portal_url = detect_captive_portal(url)

            if status in (PortalStatus.OPEN, PortalStatus.PORTAL):
                self._working_index = i

                if status == PortalStatus.PORTAL and portal_url is not None:
                    logger.warning("Captive portal detected at {url} (probed via {probe})", url=portal_url, probe=url)

                    if self._on_portal_detected:
                        self._on_portal_detected(portal_url)

                return status, portal_url
            
            logger.debug("Probe {url} resulted in ERROR, trying next if available", url=url)

        return PortalStatus.ERROR, None
