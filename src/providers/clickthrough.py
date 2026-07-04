"""Generic provider for click-through captive portals using Playwright."""

import time as time_module
from typing import Optional
import keyring

from loguru import logger
from playwright.sync_api import Browser, Page, TimeoutError as PlaywrightTimeout
from playwright_stealth import Stealth

from src.utils.portal_profile_store import PortalProfile, PortalProfileStore, RecordedStep
from .base import AuthProvider

# Instantiate the stealth engine globally
stealth = Stealth()

# JavaScript injected into every page to record user interactions.
_RECORDING_SCRIPT = """
(() => {
    if (window.__autopass_recording) return;
    window.__autopass_recording = true;
    window.__autopass_steps = [];

    function generateSelector(el) {
        if (el.id) return '#' + CSS.escape(el.id);
        if (el.tagName === 'BODY' || el.tagName === 'HTML') return el.tagName.toLowerCase();
        let path = [];
        let current = el;
        while (current && current !== document.body && current !== document.documentElement) {
            let selector = current.tagName.toLowerCase();
            if (current.id) {
                path.unshift('#' + CSS.escape(current.id));
                break;
            }
            if (current.className && typeof current.className === 'string') {
                let classes = current.className.trim().split(/\\s+/).filter(c => c.length > 0);
                if (classes.length > 0) {
                    selector += '.' + classes.map(c => CSS.escape(c)).join('.');
                }
            }
            path.unshift(selector);
            current = current.parentElement;
        }
        return path.join(' > ');
    }

    document.addEventListener('click', (e) => {
        let el = e.target;
        window.__autopass_steps.push({
            type: 'click',
            selector: generateSelector(el),
            text: (el.textContent || '').trim().slice(0, 80),
            url: location.href,
            time: Date.now()
        });
    }, true);

    document.addEventListener('change', (e) => {
        let el = e.target;
        if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
            window.__autopass_steps.push({
                type: 'fill',
                selector: generateSelector(el),
                value: el.value,
                text: '',
                url: location.href,
                time: Date.now()
            });
        }
    }, true);
})();
"""

# Capture-related pattern keywords in CSS selectors.
_CAPTCHA_PATTERNS = [
    "captcha", "verification", "verify", "sms", "otp",
    "auth_code", "authcode",
    "驗證", "驗證碼",
    "code",
]


class ClickthroughProvider(AuthProvider):
    """Handles portals that only require accepting terms of service.

    Three-phase strategy:
      1. Replay previously recorded interaction steps (if profile exists).
         Steps marked ``must_interact`` (captcha fields) cause a switch
         to partial interactive mode.
      2. Fallback to auto-detect (default selectors).
      3. Fallback to interactive mode — opens a visible browser for the
         user to complete the flow and records every interaction.
    """

    # Ordered list of selectors to try when locating the agree button.
    _AGREE_SELECTORS = [
        "button:has-text('同意')",
        "input[value*='同意']",
        "button:has-text('開始上網')",
        "button:has-text('開始使用')",
        "button:has-text('I agree')",
        "a:has-text('同意')",
        "input[type=submit][value*='同意']",
        "button:has-text('同意並開始上網')",
        "button:has-text('Accept')",
        "a:has-text('Accept')",
    ]

    def __init__(
        self,
        browser: Browser,
        playwright=None,
        executable_path: Optional[str] = None,
        profile_store: Optional[PortalProfileStore] = None,
        health_checker=None,
    ) -> None:
        self._browser = browser
        self._playwright = playwright
        self._executable_path = executable_path
        self._profile_store = profile_store
        self._health_checker = health_checker

    # ── main entry ───────────────────────────────────────────────

    def authenticate(self, portal_url: str, ssid: str) -> bool:
        """Run the three-phase authentication flow for the SSID."""
        logger.info("Authenticating {ssid} on {url}", ssid=ssid, url=portal_url)

        # Phase 1: replay recorded steps if available.
        if self._profile_store and self._profile_store.has_profile(ssid):
            profile = self._profile_store.get_profile(ssid)
            if profile and profile.steps:
                logger.info("Phase 1 — replaying {n} recorded steps for {ssid}", n=len(profile.steps), ssid=ssid)
                result = self._replay_profile(portal_url, ssid, profile)
                if result is True:  # full replay success
                    self._profile_store.record_replay_result(ssid, True)
                    return True
                logger.warning("Replay failed for {ssid}, falling back", ssid=ssid)
                self._profile_store.record_replay_result(ssid, False)

        # Phase 2: auto-detect with default selectors.
        logger.info("Phase 2 — auto-detect for {ssid}", ssid=ssid)
        success, used_selector = self._auto_detect(portal_url)
        if success:
            if used_selector and self._profile_store:
                self._profile_store.save_profile(ssid, [
                    RecordedStep(type="click", selector=used_selector, wait_after=5.0),
                ])
            return True

        # Phase 3: interactive mode — open visible browser.
        logger.info("Phase 3 — interactive login for {ssid}", ssid=ssid)
        return self._interactive_login(portal_url, ssid, start_idx=None)

    # ── Phase 2: auto-detect ─────────────────────────────────────

    def _auto_detect(self, portal_url: str) -> tuple[bool, Optional[str]]:
        """Try default selectors. Returns (success, used_selector)."""
        context = None
        page = None
        try:
            context = self._browser.new_context(
                no_viewport=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            stealth.apply_stealth_sync(page)
            page.goto(portal_url, wait_until="networkidle", timeout=30000)

            self._force_scroll_to_bottom(page)
            button = self._find_button(page, self._AGREE_SELECTORS)
            if button is None:
                return False, None

            text = button.inner_text().strip() or button.get_attribute("value") or ""
            logger.info("Clicking agree button: '{text}'", text=text[:50])

            with page.expect_navigation(wait_until="networkidle", timeout=15000):
                button.click()

            if _verify_open_internet(page, self._probe_urls):
                return True, self._AGREE_SELECTORS[self._last_matched_index]
            return False, None

        except PlaywrightTimeout:
            logger.warning("Auto-detect timeout")
            return False, None
        except Exception as exc:
            logger.error("Auto-detect error: {exc}", exc=exc)
            return False, None
        finally:
            if page is not None:
                page.close()
            if context is not None:
                context.close()

    # ── Phase 1: replay ──────────────────────────────────────────

    def _replay_profile(self, portal_url: str, ssid: str, profile: PortalProfile):
        """Replay recorded steps.

        Returns
        -------
        True
            All steps replayed and internet verified (or interactive mode succeeded).
        False
            Replay failed.
        """
        context = None
        page = None
        try:
            context = self._browser.new_context(
                no_viewport=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            stealth.apply_stealth_sync(page)
            page.goto(portal_url, wait_until="networkidle", timeout=30000)

            for i, step in enumerate(profile.steps):
                if step.must_interact:
                    logger.info("Captcha field at step {i} ({sel}) — switching to interactive", i=i + 1, sel=step.selector)
                    return self._interactive_login(portal_url, ssid, start_idx=i, profile=profile)

                logger.debug("Replay step {i}/{n}: {type} on '{sel}'", i=i + 1, n=len(profile.steps), type=step.type, sel=step.selector)
                try:
                    if step.type == "click":
                        self._force_scroll_to_bottom(page)
                        page.locator(step.selector).first.wait_for(state="visible", timeout=10000)
                        page.locator(step.selector).first.click(force=True)
                        page.wait_for_load_state("networkidle", timeout=15000)
                    elif step.type == "fill":
                        page.locator(step.selector).first.wait_for(state="visible", timeout=10000)
                        
                        fill_value = step.value
                        if step.is_password:
                            try:
                                pwd = keyring.get_password("AutoPassWiFi", f"{ssid}_{step.selector}")
                                if pwd:
                                    fill_value = pwd
                                else:
                                    logger.warning("Password not found in Credential Manager for '{sel}'", sel=step.selector)
                                    return False
                            except Exception as e:
                                logger.error("Failed to retrieve password from Credential Manager: {e}", e=e)
                                return False
                        
                        page.locator(step.selector).first.fill(fill_value)
                    if step.wait_after > 0:
                        time_module.sleep(step.wait_after)
                except Exception as exc:
                    logger.warning("Replay step {i} failed: {exc}", i=i + 1, exc=exc)
                    return False

            # Verify.
            if _verify_open_internet(page, self._probe_urls):
                logger.info("Replay successful for {ssid}", ssid=ssid)
                return True

            logger.warning("Replay completed but captive portal still detected")
            return False

        except PlaywrightTimeout:
            logger.warning("Replay timeout for {ssid}", ssid=ssid)
            return False
        except Exception as exc:
            logger.error("Replay error: {exc}", exc=exc)
            return False
        finally:
            if page is not None:
                page.close()
            if context is not None:
                context.close()

    # ── Phase 3: interactive recording ────────────────────────────

    def _interactive_login(
        self,
        portal_url: str,
        ssid: str,
        start_idx: Optional[int] = None,
        profile: Optional[PortalProfile] = None,
    ) -> bool:
        """Open a visible browser for the user to complete login manually.

        When *start_idx* is set, the corresponding *profile* steps
        before that index are replayed first; only the remaining steps
        are recorded fresh. This allows pre-filling non-captcha fields
        automatically.
        """
        visible_browser = None
        context = None
        page = None
        try:
            launch_kwargs: dict = {}
            if self._executable_path:
                launch_kwargs["executable_path"] = self._executable_path
            visible_browser = self._playwright.chromium.launch(
                headless=False,
                args=["--disable-gpu"],
                **launch_kwargs,
            )
            context = visible_browser.new_context(
                no_viewport=False,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/149.0.0.0 Safari/537.36"
                ),
            )
            page = context.new_page()
            stealth.apply_stealth_sync(page)

            # Inject recording script that survives navigation.
            page.add_init_script(_RECORDING_SCRIPT)

            logger.info("Opening portal in visible browser — please complete the login manually")
            page.goto(portal_url, wait_until="networkidle", timeout=30000)

            # Replay automated steps before the captcha breakpoint.
            if start_idx is not None and profile:
                for i in range(start_idx):
                    step = profile.steps[i]
                    if step.must_interact:
                        continue
                    try:
                        if step.type == "click":
                            self._force_scroll_to_bottom(page)
                            page.locator(step.selector).first.wait_for(state="visible", timeout=10000)
                            page.locator(step.selector).first.click(force=True)
                            page.wait_for_load_state("networkidle", timeout=15000)
                        elif step.type == "fill":
                            page.locator(step.selector).first.wait_for(state="visible", timeout=10000)
                            page.locator(step.selector).first.fill(step.value)
                        if step.wait_after > 0:
                            time_module.sleep(step.wait_after)
                    except Exception as exc:
                        logger.warning("Interactive pre-step {i} failed: {exc}", i=i + 1, exc=exc)
                logger.info("Pre-captcha steps replayed — please fill in the verification fields")

            # Poll until the portal is no longer captive.
            verified = self._poll_captive_status(timeout=300)
            if not verified:
                logger.warning("Interactive login did not complete within timeout")
                return False

            # Retrieve recorded steps.
            steps_dict = page.evaluate("window.__autopass_steps || []")
            fresh_steps = []
            for s in steps_dict:
                recorded_type = s.get("type", "")
                recorded_selector = s.get("selector", "")
                if recorded_type and recorded_selector:
                    fresh_steps.append(RecordedStep(
                        type=recorded_type,
                        selector=recorded_selector,
                        value=s.get("value", ""),
                        text=s.get("text", ""),
                        url=s.get("url", ""),
                    ))

            # Classify captcha fields.
            fresh_steps = self._classify_steps(page, fresh_steps)

            # Securely store ALL remaining non-captcha inputs
            for step in fresh_steps:
                if step.type == "fill" and not step.must_interact and step.value:
                    try:
                        keyring.set_password("AutoPassWiFi", f"{ssid}_{step.selector}", step.value)
                        step.value = "<SECURE_CREDENTIAL>"
                        step.is_password = True
                        logger.info("Saved input for '{sel}' to Credential Manager", sel=step.selector)
                    except Exception as e:
                        logger.error("Failed to save input to Credential Manager: {e}", e=e)

            # Merge: profile pre-steps + fresh recorded steps.
            merged = []
            if start_idx is not None and profile:
                merged.extend(profile.steps[:start_idx])
            merged.extend(fresh_steps)

            if merged:
                logger.info("Recorded {n} interaction steps for {ssid}", n=len(merged), ssid=ssid)
                if self._profile_store:
                    self._profile_store.save_profile(ssid, merged)
            else:
                logger.warning("No interactions were recorded for {ssid}", ssid=ssid)

            return True

        except Exception as exc:
            logger.error("Interactive login error: {exc}", exc=exc)
            return False
        finally:
            if page is not None:
                page.close()
            if context is not None:
                context.close()
            if visible_browser is not None:
                try:
                    visible_browser.close()
                except Exception:
                    pass

    # ── captcha detection ─────────────────────────────────────────

    def _classify_steps(self, page: Page, steps: list[RecordedStep]) -> list[RecordedStep]:
        """Analyze recorded fill steps and mark captcha/verification fields."""
        for step in steps:
            if step.type != "fill":
                continue
            if self._is_captcha_field(step.selector):
                step.must_interact = True
                step.value = ""  # clear stored value — it will never be reused
                logger.info("Marked '{sel}' as captcha field", sel=step.selector)
        return steps

    def _is_captcha_field(self, selector: str) -> bool:
        """Check if a CSS selector matches known captcha patterns."""
        sel_lower = selector.lower()
        for pattern in _CAPTCHA_PATTERNS:
            if pattern in sel_lower:
                return True
        return False

    # ── helpers ──────────────────────────────────────────────────

    def _poll_captive_status(self, timeout: float = 300.0, interval: float = 3.0) -> bool:
        """Poll using the current working URL until internet is open or timeout."""
        from src.core.portal_detector import detect_captive_portal, PortalStatus
        deadline = time_module.monotonic() + timeout
        while time_module.monotonic() < deadline:
            if self._health_checker:
                # Bypass HealthChecker.check() to avoid firing on_portal_detected spam.
                url = self._health_checker._probe_urls[self._health_checker._working_index]
                status, _ = detect_captive_portal(url)
                if status == PortalStatus.OPEN:
                    logger.info("Internet connection verified during interactive login")
                    return True
            time_module.sleep(interval)
        return False

    def _find_button(self, page: Page, selectors: list[str]):
        """Try each selector in order until one matches a visible element."""
        self._last_matched_index = -1
        for idx, selector in enumerate(selectors):
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    logger.debug("Found button via selector: '{sel}'", sel=selector)
                    self._last_matched_index = idx
                    # Try to remove 'disabled' attribute just in case
                    try:
                        el.evaluate("node => node.removeAttribute('disabled')")
                    except Exception:
                        pass
                    return el
            except (PlaywrightTimeout, Exception):
                continue
        return None

    def _force_scroll_to_bottom(self, page: Page):
        """Scrolls all frames and scrollable containers to the bottom to trigger 'accept TOS' scripts."""
        js = """
        () => {
            window.scrollTo(0, document.body.scrollHeight);
            document.querySelectorAll('*').forEach(el => {
                if (el.scrollHeight > el.clientHeight) {
                    let style = window.getComputedStyle(el);
                    if (style.overflowY === 'auto' || style.overflowY === 'scroll' || style.overflow === 'auto' || style.overflow === 'scroll') {
                        el.scrollTop = el.scrollHeight;
                        el.dispatchEvent(new Event('scroll', { bubbles: true }));
                    }
                }
            });
        }
        """
        for frame in page.frames:
            try:
                frame.evaluate(js)
            except Exception:
                pass
        time_module.sleep(0.5)


# ── module-level helpers ────────────────────────────────────────

def _verify_open_internet(page: Page, probe_urls: list[str]) -> bool:
    """Navigate to probe URLs and check for success content."""
    for url in probe_urls:
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 204:
                return True
            body = page.content().lower()
            if "success" in body or "captivenetwork" in body or "microsoft connect test" in body:
                return True
        except Exception:
            continue
    return False
