"""Normalizing provider voice metadata into the Voice Catalog.

Providers describe voices inconsistently and often incompletely. SPEC 2.2 makes
accent and gender our metadata rather than a TTS parameter, and API.md forbids
inventing values, so anything not stated resolves to "unknown".
"""

from __future__ import annotations

# SPEC section 9. Storage accepts the full list even though the MVP UI shows
# only what the enabled providers actually offer.
KNOWN_ACCENTS = frozenset(
    {
        "american",
        "british",
        "australian",
        "canadian",
        "irish",
        "scottish",
        "indian",
        "new_zealand",
        "south_african",
        "singaporean",
        "other",
        "unknown",
    }
)

# Deriving an accent from a documented locale is derivation, not invention.
LOCALE_TO_ACCENT = {
    "en-US": "american",
    "en-GB": "british",
    "en-AU": "australian",
    "en-CA": "canadian",
    "en-IE": "irish",
    "en-IN": "indian",
    "en-NZ": "new_zealand",
    "en-ZA": "south_african",
    "en-SG": "singaporean",
    "en-HK": "other",
    "en-KE": "other",
    "en-NG": "other",
    "en-PH": "other",
    "en-TZ": "other",
}

_ACCENT_ALIASES = {
    "us": "american",
    "usa": "american",
    "american": "american",
    "us english": "american",
    "north american": "american",
    "uk": "british",
    "gb": "british",
    "british": "british",
    "english": "british",
    "receivedpronunciation": "british",
    "australian": "australian",
    "aussie": "australian",
    "canadian": "canadian",
    "irish": "irish",
    "scottish": "scottish",
    "scotland": "scottish",
    "indian": "indian",
    "new zealand": "new_zealand",
    "south african": "south_african",
    "singaporean": "singaporean",
}

_GENDER_ALIASES = {
    "female": "female",
    "f": "female",
    "woman": "female",
    "male": "male",
    "m": "male",
    "man": "male",
    "neutral": "neutral",
    "non-binary": "neutral",
}

_AGE_ALIASES = {
    "young": "young",
    "young adult": "young",
    "child": "young",
    "teen": "young",
    "adult": "adult",
    "middle aged": "adult",
    "middle-aged": "adult",
    "old": "mature",
    "mature": "mature",
    "senior": "mature",
}


def normalize_accent(value: str | None, locale: str | None = None) -> str:
    """Map a provider's accent label, falling back to the locale."""
    if value:
        key = value.strip().lower().replace("_", " ")
        mapped = _ACCENT_ALIASES.get(key)
        if mapped:
            return mapped
        if key.replace(" ", "_") in KNOWN_ACCENTS:
            return key.replace(" ", "_")
    if locale:
        by_locale = LOCALE_TO_ACCENT.get(locale)
        if by_locale:
            return by_locale
    return "unknown"


def normalize_gender(value: str | None) -> str:
    if not value:
        return "unknown"
    return _GENDER_ALIASES.get(value.strip().lower(), "unknown")


def normalize_age_group(value: str | None) -> str:
    if not value:
        return "unknown"
    return _AGE_ALIASES.get(value.strip().lower(), "unknown")


def normalize_language(locale: str | None) -> str:
    if not locale:
        return "en"
    return locale.split("-")[0].lower()
