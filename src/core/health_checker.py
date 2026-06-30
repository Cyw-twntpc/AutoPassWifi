"""Check internet connectivity by probing a known HTTP URL."""

from typing import Callable, Optional

from loguru import logger

from .portal_detector import detect_captive_portal


class HealthChecker:
    """Run a one-shot connectivity probe and fire a callback if captive."""

    def __init__(
        self,
        probe_url: str = "http://captive.apple.com",
    ) -> None:
        self._probe_url = probe_url
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
        portal_url = detect_captive_portal(self._probe_url)

        if portal_url is None:
            return None

        logger.warning("Captive portal detected at {url}", url=portal_url)

        if self._on_portal_detected:
            self._on_portal_detected(portal_url)

        return portal_url
