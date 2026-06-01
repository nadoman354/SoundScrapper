from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse


DIRECT_PROVIDER_PRIORITY = {
    "freesound": 0,
    "jamendo": 1,
}
OPENVERSE_PRIORITY = 2


def canonical_provider(value: str | None) -> str:
    normalized = (value or "").strip().lower().replace("-", "_")
    aliases = {
        "freesound_org": "freesound",
        "freesound": "freesound",
        "jamendo": "jamendo",
        "wikimedia_commons": "wikimedia",
        "wikimedia": "wikimedia",
        "ccmixter": "cc_mixter",
        "cc_mixter": "cc_mixter",
    }
    return aliases.get(normalized, normalized or "unknown")


def stable_sound_id(provider: str, source_id: str | int) -> int:
    canonical = canonical_provider(provider)
    source = str(source_id).strip()
    if canonical == "freesound" and source.isdigit():
        return int(source)

    digest = hashlib.sha256(f"{canonical}:{source}".encode("utf-8")).hexdigest()
    return 1_000_000_000 + (int(digest[:12], 16) % 1_000_000_000)


def source_key(provider: str, source_id: str | int) -> tuple[str, str]:
    return canonical_provider(provider), str(source_id).strip()


def provider_priority(provider: str, api_priority: int | None = None) -> int:
    if api_priority is not None:
        return api_priority
    return DIRECT_PROVIDER_PRIORITY.get(canonical_provider(provider), OPENVERSE_PRIORITY)


def extract_source_id(provider: str, fallback: str | int | None, url: str | None = None) -> str:
    canonical = canonical_provider(provider)
    if url:
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        if canonical == "freesound":
            match = re.search(r"(?:^|/)s/(\d+)", path)
            if match:
                return match.group(1)
        if canonical == "jamendo":
            match = re.search(r"(?:^|/)track/(\d+)", path)
            if match:
                return match.group(1)

    if fallback is not None and str(fallback).strip():
        return str(fallback).strip()
    if url:
        return url
    return "unknown"
