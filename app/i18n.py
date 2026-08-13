"""Minimal translation lookup.

v1 ships English only, but no user-facing string is hardcoded in a template: every one
goes through `t()` against locales/<lang>.json. Adding a language is dropping in a new
JSON file — no template edits, no code changes.
"""

import json
from functools import lru_cache

from app.config import BASE_DIR

LOCALES_DIR = BASE_DIR / "locales"
DEFAULT_LANG = "en"


@lru_cache
def catalog(lang: str = DEFAULT_LANG) -> dict[str, str]:
    path = LOCALES_DIR / f"{lang}.json"
    if not path.is_file():
        path = LOCALES_DIR / f"{DEFAULT_LANG}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def available_languages() -> list[str]:
    return sorted(p.stem for p in LOCALES_DIR.glob("*.json"))


def negotiate(accept_language: str | None) -> str:
    """Pick the best available language from an Accept-Language header."""
    if not accept_language:
        return DEFAULT_LANG
    available = set(available_languages())
    for chunk in accept_language.split(","):
        tag = chunk.split(";")[0].strip().lower()
        if not tag:
            continue
        if tag in available:
            return tag
        primary = tag.split("-")[0]
        if primary in available:
            return primary
    return DEFAULT_LANG


def translate(key: str, lang: str = DEFAULT_LANG, **params: object) -> str:
    text = catalog(lang).get(key) or catalog(DEFAULT_LANG).get(key) or key
    if params:
        try:
            return text.format(**params)
        except (KeyError, IndexError):
            return text
    return text
