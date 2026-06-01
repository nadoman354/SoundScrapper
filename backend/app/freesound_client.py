from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from backend.app.schemas import LicenseFilter, SoundSearchResult
from backend.app.source_identity import stable_sound_id


FREESOUND_FIELDS = "id,name,username,license,duration,tags,previews,url,description,num_downloads"


class FreesoundConfigurationError(RuntimeError):
    """Raised when Freesound cannot be called with the current settings."""


class FreesoundClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str = "https://freesound.org",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
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
        if not self.api_key:
            raise FreesoundConfigurationError("FREESOUND_API_KEY is not configured.")

        params = {
            "query": query,
            "fields": FREESOUND_FIELDS,
            "page_size": str(page_size),
            "filter": build_filter(license_filter, min_duration, max_duration),
        }
        headers = {"Authorization": f"Token {self.api_key}"}

        async with httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=15,
            transport=self.transport,
        ) as client:
            response = await client.get("/apiv2/search/", params=params)
            response.raise_for_status()
            payload = response.json()

        return [normalize_sound(item) for item in payload.get("results", [])]


def build_filter(license_filter: LicenseFilter, min_duration: float, max_duration: float) -> str:
    filters = [f"duration:[{min_duration} TO {max_duration}]"]

    if license_filter == "cc0":
        filters.append('license:"Creative Commons 0"')
    elif license_filter == "commercial":
        filters.append('(license:"Creative Commons 0" OR license:"Attribution")')

    return " ".join(filters)


def normalize_sound(item: Mapping[str, Any]) -> SoundSearchResult:
    source_id = str(item.get("id", 0))
    previews = item.get("previews")
    preview_url = _select_preview(previews if isinstance(previews, Mapping) else {})

    return SoundSearchResult(
        id=stable_sound_id("freesound", source_id),
        name=str(item.get("name") or "Untitled sound"),
        username=str(item.get("username") or ""),
        license=str(item.get("license") or ""),
        duration=float(item.get("duration") or 0),
        tags=[str(tag) for tag in item.get("tags", []) if tag],
        preview_url=preview_url,
        url=str(item.get("url")) if item.get("url") else None,
        description=str(item.get("description")) if item.get("description") else None,
        source_provider="freesound",
        source_id=source_id,
        source_url=str(item.get("url")) if item.get("url") else None,
        creator_url=f"https://freesound.org/people/{item.get('username')}/"
        if item.get("username")
        else None,
        attribution_text=_attribution_text(item),
        download_url=preview_url,
        download_allowed=bool(preview_url),
        download_count=_optional_int(item.get("num_downloads")),
    )


def _select_preview(previews: Mapping[str, Any]) -> str | None:
    for key in ("preview-hq-mp3", "preview-lq-mp3", "preview-hq-ogg", "preview-lq-ogg"):
        value = previews.get(key)
        if value:
            return str(value)
    return None


def _attribution_text(item: Mapping[str, Any]) -> str:
    name = str(item.get("name") or "Untitled sound")
    username = str(item.get("username") or "Unknown creator")
    license_name = str(item.get("license") or "Unknown license")
    return f"{name} by {username} ({license_name})"


def _optional_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
