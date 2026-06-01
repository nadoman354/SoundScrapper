from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from backend.app.preview_cache import is_allowed_preview_url
from backend.app.schemas import LicenseFilter, SoundSearchResult
from backend.app.source_identity import canonical_provider, extract_source_id, stable_sound_id


class OpenverseClient:
    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        base_url: str = "https://api.openverse.org",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = self._normalize_base_url(base_url)
        self.transport = transport

    async def search(
        self,
        query: str,
        license_filter: LicenseFilter,
        min_duration: float,
        max_duration: float,
        page_size: int,
    ) -> list[SoundSearchResult]:
        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=15,
            transport=self.transport,
        ) as client:
            response = await client.get(
                "/audio/",
                params={
                    "q": query,
                    "page_size": str(page_size),
                },
                headers=await self._auth_headers(client),
            )
            response.raise_for_status()
            payload = response.json()

        results = [normalize_audio(item) for item in payload.get("results", [])]
        return [
            result
            for result in results
            if _matches_duration(result, min_duration, max_duration)
            and _matches_license_filter(result, license_filter)
        ]

    async def _auth_headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not self.client_id or not self.client_secret:
            return {}

        response = await client.post(
            "/auth_tokens/token/",
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        response.raise_for_status()
        token = response.json().get("access_token")
        return {"Authorization": f"Bearer {token}"} if token else {}

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/v1"):
            return normalized
        return f"{normalized}/v1"


def normalize_audio(item: Mapping[str, Any]) -> SoundSearchResult:
    provider = canonical_provider(str(item.get("source") or item.get("provider") or "openverse"))
    landing_url = str(item.get("foreign_landing_url") or "") or None
    source_id = extract_source_id(
        provider,
        item.get("foreign_identifier") or item.get("id"),
        landing_url,
    )
    audio_url = str(item.get("url") or "") or None
    preview_url = audio_url if audio_url and is_allowed_preview_url(audio_url) else None
    duration = _duration_seconds(item.get("duration"))
    license_name = _license_label(item.get("license"), item.get("license_version"))

    return SoundSearchResult(
        id=stable_sound_id(provider, source_id),
        name=str(item.get("title") or "Untitled audio"),
        username=str(item.get("creator") or ""),
        license=license_name,
        duration=duration,
        tags=_tags(item),
        preview_url=preview_url,
        url=landing_url or audio_url,
        description=str(item.get("description")) if item.get("description") else None,
        source_provider=provider,
        source_id=source_id,
        source_url=landing_url or audio_url,
        license_url=str(item.get("license_url")) if item.get("license_url") else None,
        creator_url=str(item.get("creator_url")) if item.get("creator_url") else None,
        attribution_text=str(item.get("attribution")) if item.get("attribution") else None,
        download_url=preview_url,
        download_allowed=bool(preview_url),
    )


def _duration_seconds(value: Any) -> float:
    duration = float(value or 0)
    if duration > 1000:
        return duration / 1000
    return duration


def _tags(item: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for field in ("tags", "genres"):
        raw = item.get(field)
        if not isinstance(raw, list):
            continue
        for tag in raw:
            if isinstance(tag, Mapping):
                name = tag.get("name")
                if name:
                    values.append(str(name))
            elif tag:
                values.append(str(tag))
    return list(dict.fromkeys(values))


def _license_label(license_slug: Any, version: Any) -> str:
    slug = str(license_slug or "").upper()
    if slug == "CC0":
        return "CC0"
    if slug:
        version_text = f" {version}" if version else ""
        return f"CC {slug}{version_text}"
    return "Openverse license"


def _matches_duration(
    result: SoundSearchResult,
    min_duration: float,
    max_duration: float,
) -> bool:
    return result.duration == 0 or min_duration <= result.duration <= max_duration


def _matches_license_filter(result: SoundSearchResult, license_filter: LicenseFilter) -> bool:
    license_text = result.license.lower()
    if license_filter == "any":
        return True
    if license_filter == "cc0":
        return "cc0" in license_text
    return "nc" not in license_text
