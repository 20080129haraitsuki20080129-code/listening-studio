from __future__ import annotations

from app.domain.errors import UnsupportedProvider

from .base import TTSProvider


class TTSProviderRegistry:
    def __init__(self, providers: dict[str, TTSProvider] | None = None) -> None:
        self._providers: dict[str, TTSProvider] = dict(providers or {})

    def register(self, provider: TTSProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, provider: str) -> TTSProvider:
        if provider not in self._providers:
            raise UnsupportedProvider(provider)
        return self._providers[provider]

    def names(self) -> list[str]:
        return sorted(self._providers)

    def __contains__(self, provider: object) -> bool:
        return provider in self._providers
