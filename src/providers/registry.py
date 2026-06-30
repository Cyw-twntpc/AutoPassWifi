"""Registry holding available auth providers."""

from typing import Optional

from .base import AuthProvider


class ProviderRegistry:
    """Manages available auth providers."""

    def __init__(self) -> None:
        self._providers: list[AuthProvider] = []

    def register(self, provider: AuthProvider) -> None:
        """Register a provider."""
        self._providers.append(provider)

    def get_fallback(self) -> Optional[AuthProvider]:
        """Return the first registered provider, or None."""
        return self._providers[0] if self._providers else None
