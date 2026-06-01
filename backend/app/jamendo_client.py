from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from backend.app.schemas import LicenseFilter, SoundSearchResult
from backend.app.source_identity import stable_sound_id


class JamendoConfigurationError(RuntimeError):
    """Raised when Jamendo cannot be called with the current settings."""


class JamendoClient:
    def __init__(
        self,
        client_id: str | None,
        base_url: str = "https://api.jamendo.com/v3.0",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    async def search(
        self,
        query: str,
        license_filter: LicenseFilter,
        min_duration: float,
        max_duration: float,
        page_size: int,
    ) -> list[SoundSearchResult]:
        if not self.client_id:
            raise JamendoConfigurationError("JAMENDO_CLIENT_ID is not configured.")

        params = {
            "client_id": self.client_id,
            "format": "json",
            "limit": str(page_size),
            "search": query,
            "order": "relevance",
            "include": "licenses+musicinfo",
            "audioformat": "mp31",
            "audiodlformat": "mp32",
            "durationbetween": f"{int(min_duration)}_{int(max_duration)}",
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=15,
            transport=self.transport,
        ) as client:
            response = await client.get("/tracks/", params=params)
            response.raise_for_status()
            payload = response.json()

        results = [normalize_track(item) for item in payload.get("results", [])]
        return [result for result in results if _matches_license_filter(result, license_filter)]


def normalize_track(item: Mapping[str, Any]) -> SoundSearchResult:
    source_id = str(item.get("id") or "0")
    license_url = str(item.get("license_ccurl") or item.get("license_url") or "")
    license_name = _license_label(license_url)
    audio_url = str(item.get("audio") or "") or None
    download_url = str(item.get("audiodownload") or "") or None
    download_allowed = bool(item.get("audiodownload_allowed")) and bool(download_url)
    source_url = str(item.get("shareurl") or item.get("shorturl") or "") or None
    artist_id = item.get("artist_id")
    artist_slug = str(item.get("artist_idstr") or "").strip()
    artist_url = (
        f"https://www.jamendo.com/artist/{artist_id}/{artist_slug}"
        if artist_id and artist_slug
        else None
    )

    return SoundSearchResult(
        id=stable_sound_id("jamendo", source_id),
        name=str(item.get("name") or "Untitled track"),
        username=str(item.get("artist_name") or ""),
        license=license_name,
        duration=float(item.get("duration") or 0),
        tags=_tags(item),
        preview_url=audio_url,
        url=source_url,
        description=str(item.get("album_name") or "") or None,
        source_provider="jamendo",
        source_id=source_id,
        source_url=source_url,
        license_url=license_url or None,
        creator_url=artist_url,
        attribution_text=_attribution_text(item, license_name),
        download_url=download_url if download_allowed else None,
        download_allowed=download_allowed,
    )


def _tags(item: Mapping[str, Any]) -> list[str]:
    musicinfo = item.get("musicinfo") if isinstance(item.get("musicinfo"), Mapping) else {}
    tag_sources = [
        musicinfo.get("tags", {}),
        musicinfo.get("vocalinstrumental", ""),
        musicinfo.get("speed", ""),
    ]
    tags: list[str] = []
    for source in tag_sources:
        if isinstance(source, Mapping):
            for values in source.values():
                if isinstance(values, list):
                    tags.extend(str(value) for value in values if value)
                elif values:
                    tags.append(str(values))
        elif source:
            tags.append(str(source))
    return list(dict.fromkeys(tags))


def _license_label(license_url: str) -> str:
    lower = license_url.lower()
    if "zero" in lower or "publicdomain/zero" in lower:
        return "CC0"
    if "by-nc-nd" in lower:
        return "CC BY-NC-ND"
    if "by-nc-sa" in lower:
        return "CC BY-NC-SA"
    if "by-nc" in lower:
        return "CC BY-NC"
    if "by-nd" in lower:
        return "CC BY-ND"
    if "by-sa" in lower:
        return "CC BY-SA"
    if "by" in lower:
        return "CC BY"
    return "Jamendo license"


def _attribution_text(item: Mapping[str, Any], license_name: str) -> str:
    title = str(item.get("name") or "Untitled track")
    artist = str(item.get("artist_name") or "Unknown artist")
    return f"{title} by {artist} ({license_name})"


def _matches_license_filter(result: SoundSearchResult, license_filter: LicenseFilter) -> bool:
    license_text = result.license.lower()
    if license_filter == "any":
        return True
    if license_filter == "cc0":
        return "cc0" in license_text
    return "nc" not in license_text
