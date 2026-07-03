"""Check internet connectivity by probing a known HTTP URL."""

from typing import Callable, Optional

from loguru import logger

from .portal_detector import detect_captive_portal


class HealthChecker:
    """Run a one-shot connectivity probe and fire a callback if captive."""

    def __init__(
        self,
        probe_urls: Optional[list[str]] = None,
    ) -> None:
        self._probe_urls = probe_urls or ["http://captive.apple.com", "http://www.msftconnecttest.com/connecttest.txt"]
        self._on_portal_detected: Optional[Callable[[str], None]] = None

    def on_portal_detected(self, callback: Callable[[str], None]) -> None:
        self._on_portal_detected = callback

    def check(self) -> Optional[str]:
        """Probe connectivity.

        Returns
        -------
        str or None
            The captive portal URL if captive, None if internet is open.
        """
        for url in self._probe_urls:
            portal_url = detect_captive_portal(url)

            if portal_url is not None:
                logger.warning("Captive portal detected at {url} (probed via {probe})", url=portal_url, probe=url)

                if self._on_portal_detected:
                    self._on_portal_detected(portal_url)

                return portal_url

        return None
