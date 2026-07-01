"""Engine class — wires all components together."""

import math
import os
import sys
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from src.core.authenticator import Authenticator
from src.core.connection_monitor import ConnectionMonitor
from src.core.health_checker import HealthChecker
from src.core.portal_detector import detect_captive_portal
from src.providers.clickthrough import ClickthroughProvider
from src.providers.registry import ProviderRegistry
from src.utils.config import AppConfig
from src.core.connection_monitor import query_current_ssid as get_current_ssid
from src.utils.portal_profile_store import PortalProfileStore
from src.utils.session_tracker import SessionTracker


class Engine:
    """Main autopasswifi engine that wires all components together."""

    def __init__(self, config: AppConfig, playwright_instance=None) -> None:
        self._config = config
        self._running = False
        self._playwright = playwright_instance
        self._browser = None

        # Resolve chromium path for frozen mode (full browser, not headless shell).
        self._browser_path: Optional[str] = None
        if getattr(sys, "frozen", False):
            exe = Path(sys.executable).parent / "chromium-1228" / "chrome-win64" / "chrome.exe"
            if exe.exists():
                self._browser_path = str(exe)

        launch_kwargs: dict = {}
        if self._browser_path:
            launch_kwargs["executable_path"] = self._browser_path
        self._browser = self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-gpu"],
            **launch_kwargs,
        )

        # Session tracker (persisted per-SSID history).
        scfg = self._config.session
        self._session_tracker = SessionTracker(
            data_file=scfg.data_file,
            default_interval=scfg.default_interval,
            overrun_interval=scfg.overrun_interval,
            stable_threshold=scfg.stable_threshold,
            cubic_k=scfg.cubic_k,
        )

        # Build provider registry.
        self._registry = ProviderRegistry()
        profile_store = PortalProfileStore()
        clickthrough_provider = ClickthroughProvider(
            browser=self._browser,
            playwright=self._playwright,
            executable_path=self._browser_path,
            profile_store=profile_store,
        )
        self._registry.register(clickthrough_provider)

        # Core modules.
        self._connection_monitor = ConnectionMonitor()
        self._authenticator = Authenticator(self._registry)
        self._health_checker = HealthChecker(probe_url=config.probe_url)

        # Health-check scheduling state.
        self._next_check_at: float = 0.0      # monotonic time for next probe

        # Wire callbacks.
        self._connection_monitor.on_ssid_changed(self._on_ssid_changed)
        self._health_checker.on_portal_detected(self._on_portal_detected)

    # ── retry wrappers (value-based, not exception-based) ──────

    def _detect_portal_with_retry(self, probe_url: str) -> Optional[str]:
        """Probe for captive portal, retrying up to 3 times on None."""
        for attempt in range(3):
            result = detect_captive_portal(probe_url)
            if result is not None:
                return result
            if attempt < 2:
                time.sleep(1.0 * (2.0 ** attempt))
        return None

    def _authenticate_with_retry(self, ssid: str, portal_url: str) -> bool:
        """Run authentication, retrying up to 3 times on failure."""
        for attempt in range(3):
            if self._authenticator.authenticate(ssid, portal_url):
                return True
            if attempt < 2:
                time.sleep(1.0 * (2.0 ** attempt))
        return False

    # ── callbacks ───────────────────────────────────────────────

    def _on_ssid_changed(self, old_ssid: Optional[str], new_ssid: Optional[str]) -> None:
        """Called when the WiFi SSID changes."""
        try:
            # Record disconnect for the old SSID.
            if old_ssid is not None:
                self._session_tracker.record_disconnect(old_ssid)

            if new_ssid is None:
                logger.info("WiFi disconnected")
                return

            logger.info("Connected to SSID: {ssid}", ssid=new_ssid)

            # Check if behind a captive portal and authenticate.
            portal_url = self._detect_portal_with_retry(self._config.probe_url)
            if portal_url is None:
                return

            # Both known and unknown SSID go through the registry.
            success = self._authenticate_with_retry(new_ssid, portal_url)

            if success:
                self._session_tracker.record_auth(new_ssid)
                self._schedule_next_check(new_ssid)
        except Exception as exc:
            logger.error("_on_ssid_changed failed: {exc}", exc=exc)

    def _on_portal_detected(self, portal_url: str) -> None:
        """Called when the health checker detects a captive portal."""
        try:
            ssid = self._connection_monitor.current_ssid
            if ssid:
                logger.info("Portal re-detected on {ssid}, re-authenticating", ssid=ssid)
                self._session_tracker.record_reset(ssid)
                success = self._authenticate_with_retry(ssid, portal_url)
                if success:
                    self._session_tracker.record_auth(ssid)
                    self._schedule_next_check(ssid)
                else:
                    # Auth failed — retry soon.
                    self._next_check_at = time.monotonic() + 30.0
        except Exception as exc:
            logger.error("_on_portal_detected failed: {exc}", exc=exc)

    # ── scheduling ──────────────────────────────────────────────

    def _schedule_next_check(self, ssid: str) -> None:
        """Calculate and schedule the next health check for the SSID."""
        interval = self._session_tracker.get_interval(ssid)
        if math.isinf(interval):
            logger.info("Health checks stopped for {ssid} (stable)", ssid=ssid)
            self._next_check_at = float("inf")
        else:
            self._next_check_at = time.monotonic() + interval
            logger.debug(
                "Next health check for {ssid} in {interval:.0f}s",
                ssid=ssid,
                interval=interval,
            )

    # ── main loop ───────────────────────────────────────────────

    def run(self) -> None:
        """Main loop: process WiFi events and health-check on a dynamic schedule."""
        self._running = True
        self._connection_monitor.start()

        # One-shot initial SSID to bootstrap state without waiting for an event.
        initial_ssid = get_current_ssid()
        self._connection_monitor.set_initial_ssid(initial_ssid)
        if initial_ssid:
            self._on_ssid_changed(None, initial_ssid)

        logger.info("autopasswifi started")

        while self._running:
            try:
                now = time.monotonic()

                # Phase 1: process WiFi events (blocks up to 1s — serves as heartbeat).
                self._connection_monitor.poll(timeout=1.0)
                current_ssid = self._connection_monitor.current_ssid

                # Phase 2: health check (only if connected to a WiFi network).
                if (
                    current_ssid is not None
                    and now >= self._next_check_at
                ):
                    portal_url = self._health_checker.check()

                    if portal_url is None:
                        # Internet is open — possibly mark as stable.
                        record = self._session_tracker.get_record(current_ssid)
                        elapsed = 0.0
                        if record.last_auth_at is not None:
                            elapsed = time.time() - record.last_auth_at
                        if elapsed >= self._session_tracker.stable_threshold and not record.stable:
                            self._session_tracker.mark_stable(current_ssid)

                        self._schedule_next_check(current_ssid)
            except Exception as exc:
                logger.error("Engine loop error: {exc}", exc=exc)
                self._next_check_at = time.monotonic() + 30.0
                time.sleep(1)

        self._connection_monitor.stop()
        logger.info("Engine stopped")

    def stop(self) -> None:
        """Signal the engine to stop and release resources."""
        self._running = False
        self._connection_monitor.stop()
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
