"""Detect captive portal by probing a known HTTP URL."""

from typing import Optional

import httpx


def detect_captive_portal(probe_url: str = "http://captive.apple.com") -> Optional[str]:
    """Probe a known HTTP URL and detect if we are behind a captive portal.

    Returns the portal redirect URL if captive, or None if internet is open.
    """
    try:
        with httpx.Client(timeout=10, follow_redirects=False) as client:
            resp = client.get(probe_url)

            # 204 from the actual probe endpoint means open internet.
            if resp.status_code == 204:
                return None

            # 200 — check body to distinguish Apple's "Success" from portal content.
            if resp.status_code == 200:
                body = resp.text
                if "Success" in body:
                    return None
                return resp.url.__str__()

            # 3xx redirect to a portal page.
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("location")
                if location:
                    return location

            return resp.url.__str__()

    except httpx.RequestError:
        # Network not reachable / not connected.
        return None
