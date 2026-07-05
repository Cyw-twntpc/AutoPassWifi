"""Detect captive portal by probing a known HTTP URL."""

import concurrent.futures
import enum
from typing import Optional

import httpx


class PortalStatus(enum.Enum):
    OPEN = "OPEN"
    PORTAL = "PORTAL"
    ERROR = "ERROR"


def detect_captive_portal(probe_url: str = "http://captive.apple.com") -> tuple[PortalStatus, Optional[str]]:
    """Probe a known HTTP URL and detect if we are behind a captive portal.

    Returns:
        tuple[PortalStatus, Optional[str]]: The status and the portal URL if detected.
    """
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            resp = client.get(probe_url)

            # 204 from the actual probe endpoint means open internet.
            if resp.status_code == 204:
                return PortalStatus.OPEN, None

            # 200 — check body to distinguish open internet from portal content.
            if resp.status_code == 200:
                body = resp.text.lower()
                if "success" in body or "microsoft connect test" in body or "microsoft ncsi" in body:
                    return PortalStatus.OPEN, None
                return PortalStatus.PORTAL, resp.url.__str__()

            # 3xx redirect to a portal page.
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if location:
                    return PortalStatus.PORTAL, location

            return PortalStatus.PORTAL, resp.url.__str__()

    except httpx.RequestError:
        # Network not reachable / not connected.
        return PortalStatus.ERROR, None


def concurrent_detect_captive_portal(probe_urls: list[str]) -> tuple[PortalStatus, Optional[str]]:
    """Probe multiple known HTTP URLs concurrently. Returns the first definitive result.

    Returns:
        tuple[PortalStatus, Optional[str]]: The status and the portal URL if detected.
    """
    if not probe_urls:
        return PortalStatus.ERROR, None

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(probe_urls))
    future_to_url = {executor.submit(detect_captive_portal, url): url for url in probe_urls}
    
    for future in concurrent.futures.as_completed(future_to_url):
        try:
            status, portal_url = future.result()
            if status in (PortalStatus.OPEN, PortalStatus.PORTAL):
                executor.shutdown(wait=False)
                return status, portal_url
        except Exception:
            pass
            
    # All failed
    executor.shutdown(wait=False)
    return PortalStatus.ERROR, None
