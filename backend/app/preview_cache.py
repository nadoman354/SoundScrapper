from __future__ import annotations

import hashlib
from pathlib import Path
from urllib.parse import urlparse

import httpx


ALLOWED_PREVIEW_HOST_SUFFIXES = (
    "freesound.org",
    "jamendo.com",
    "wikimedia.org",
)
MIME_BY_SUFFIX = {
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
}


class PreviewCacheError(RuntimeError):
    """Raised when a preview URL cannot be cached safely."""


def is_allowed_preview_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return parsed.scheme == "https" and any(
        hostname == suffix or hostname.endswith(f".{suffix}")
        for suffix in ALLOWED_PREVIEW_HOST_SUFFIXES
    )


def cached_preview_path(cache_dir: Path, freesound_id: int, preview_url: str) -> Path:
    parsed = urlparse(preview_url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix not in MIME_BY_SUFFIX:
        suffix = ".mp3"
    digest = hashlib.sha256(preview_url.encode("utf-8")).hexdigest()[:12]
    return cache_dir / f"{freesound_id}-{digest}{suffix}"


def media_type_for_path(path: Path) -> str:
    return MIME_BY_SUFFIX.get(path.suffix.lower(), "application/octet-stream")


async def cache_preview_audio(
    cache_dir: Path,
    freesound_id: int,
    preview_url: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> Path:
    if not is_allowed_preview_url(preview_url):
        raise PreviewCacheError("Only approved source preview URLs can be cached.")

    cache_dir.mkdir(parents=True, exist_ok=True)
    target_path = cached_preview_path(cache_dir, freesound_id, preview_url)
    if target_path.exists() and target_path.stat().st_size > 0:
        return target_path

    async with httpx.AsyncClient(timeout=20, transport=transport, follow_redirects=True) as client:
        response = await client.get(preview_url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if not content_type.startswith("audio/"):
            raise PreviewCacheError("Preview URL did not return audio content.")
        target_path.write_bytes(response.content)

    return target_path
