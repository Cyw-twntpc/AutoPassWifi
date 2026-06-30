"""Abstract base class for captive portal authentication providers."""

from abc import ABC, abstractmethod


class AuthProvider(ABC):
    """Each provider handles authentication for a captive portal."""

    @abstractmethod
    def authenticate(self, portal_url: str, ssid: str) -> bool:
        """Navigate the captive portal flow and return True if authenticated.

        The *ssid* parameter allows providers to look up per-SSID profiles
        for step replay or interactive recording.
        """
        ...
