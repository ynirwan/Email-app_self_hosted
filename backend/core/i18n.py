# backend/core/i18n.py
"""
Minimal i18n helper.

- Loads JSON catalogs from backend/locales/{lang}.json on first use.
- Returns the requested key in the user's language, falling back to English,
  then to the key itself if nothing is found.
- Supports str.format()-style interpolation: t("welcome", lang, name="Yogesh").

Backend uses this for things like email subjects, system-generated email body
strings, and API error messages that the user will see. UI strings live in
the frontend catalog.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "es", "fr", "de", "zh", "hi", "ar", "ru")

_LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"


@lru_cache(maxsize=len(SUPPORTED_LANGUAGES))
def _load_catalog(lang: str) -> dict[str, str]:
    """Load one language file. Cached for the process lifetime."""
    path = _LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        logger.warning("Locale file missing: %s", path)
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            logger.error("Locale file %s is not a JSON object", path)
            return {}
        return data
    except (OSError, json.JSONDecodeError) as e:
        logger.error("Failed to load locale %s: %s", path, e)
        return {}


def normalize_language(lang: str | None) -> str:
    """Coerce arbitrary input to a supported language code."""
    if not lang:
        return DEFAULT_LANGUAGE
    code = lang.strip().lower().split("-")[0]  # 'en-US' -> 'en'
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def t(key: str, lang: str | None = None, /, **kwargs: Any) -> str:
    """
    Translate `key` into `lang`. Falls back to English, then to the key itself.

    Usage:
        t("campaign.scheduled", user["language"], when=eta_str)
    """
    primary = normalize_language(lang)
    catalog = _load_catalog(primary)
    template = catalog.get(key)

    if template is None and primary != DEFAULT_LANGUAGE:
        template = _load_catalog(DEFAULT_LANGUAGE).get(key)

    if template is None:
        return key  # explicit miss — caller can detect and log if needed

    if not kwargs:
        return template
    try:
        return template.format(**kwargs)
    except (KeyError, IndexError) as e:
        logger.warning("i18n format error for key=%s lang=%s: %s", key, primary, e)
        return template


def is_supported(lang: str | None) -> bool:
    """Public helper for input validation in routes/Pydantic."""
    return normalize_language(lang) == (lang or "").strip().lower().split("-")[0]