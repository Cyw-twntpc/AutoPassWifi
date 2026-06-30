"""Orchestrate captive portal authentication."""

from loguru import logger

from src.providers.registry import ProviderRegistry


class Authenticator:
    """Handle the full authentication flow for a given SSID."""

    def __init__(self, registry: ProviderRegistry) -> None:
        self._registry = registry

    def authenticate(self, ssid: str, portal_url: str) -> bool:
        """Run the provider's authentication flow for the given SSID.

        Returns True on success, False on failure.
        """
        provider = self._registry.get_fallback()
        if provider is None:
            logger.warning("No provider available for SSID: {ssid}", ssid=ssid)
            return False

        logger.info("Authenticating on {ssid} via {name}", ssid=ssid, name=type(provider).__name__)
        success = provider.authenticate(portal_url, ssid)

        if success:
            logger.info("Authentication succeeded on {ssid}", ssid=ssid)
        else:
            logger.warning("Authentication failed on {ssid}", ssid=ssid)

        return success
