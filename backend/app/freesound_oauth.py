from __future__ import annotations

import mimetypes
import time
from dataclasses import dataclass
from email.message import Message
from pathlib import Path
from urllib.parse import urlencode

import httpx

from backend.app.config import Settings


class FreesoundOAuthConfigurationError(RuntimeError):
    """Raised when Freesound OAuth credentials are not configured."""


@dataclass(frozen=True)
class FreesoundTokenPayload:
    access_token: str
    refresh_token: str
    expires_at: int


@dataclass(frozen=True)
class FreesoundOriginalDownload:
    path: Path
    filename: str
    media_type: str


def ensure_oauth_configured(settings: Settings) -> None:
    if not settings.freesound_client_id or not settings.freesound_client_secret:
        raise FreesoundOAuthConfigurationError(
            "FREESOUND_CLIENT_ID and FREESOUND_CLIENT_SECRET are required."
        )


def freesound_authorize_url(settings: Settings, state: str) -> str:
    ensure_oauth_configured(settings)
    return (
        f"{settings.freesound_base_url.rstrip('/')}/apiv2/oauth2/authorize/?"
        + urlencode(
            {
                "client_id": settings.freesound_client_id,
                "response_type": "code",
                "state": state,
            }
        )
    )


async def exchange_authorization_code(
    settings: Settings,
    code: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FreesoundTokenPayload:
    ensure_oauth_configured(settings)
    return await _request_token(
        settings,
        {
            "client_id": settings.freesound_client_id or "",
            "client_secret": settings.freesound_client_secret or "",
            "grant_type": "authorization_code",
            "code": code,
        },
        transport=transport,
    )


async def refresh_access_token(
    settings: Settings,
    refresh_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FreesoundTokenPayload:
    ensure_oauth_configured(settings)
    return await _request_token(
        settings,
        {
            "client_id": settings.freesound_client_id or "",
            "client_secret": settings.freesound_client_secret or "",
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        fallback_refresh_token=refresh_token,
        transport=transport,
    )


async def fetch_freesound_me(
    settings: Settings,
    access_token: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict:
    async with httpx.AsyncClient(
        base_url=settings.freesound_base_url,
        timeout=15,
        transport=transport,
        follow_redirects=True,
    ) as client:
        response = await client.get(
            "/apiv2/me/",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()
        return response.json()


async def download_freesound_original(
    settings: Settings,
    source_id: str,
    access_token: str,
    name: str,
    transport: httpx.AsyncBaseTransport | None = None,
) -> FreesoundOriginalDownload:
    output_dir = settings.preview_cache_dir / "freesound-originals"
    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        base_url=settings.freesound_base_url,
        timeout=60,
        transport=transport,
        follow_redirects=True,
    ) as client:
        response = await client.get(
            f"/apiv2/sounds/{source_id}/download/",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        response.raise_for_status()

    media_type = response.headers.get("content-type", "application/octet-stream").split(";")[0]
    filename = _content_disposition_filename(response.headers.get("content-disposition", ""))
    filename = filename or name or f"freesound-{source_id}"
    suffix = Path(filename).suffix or mimetypes.guess_extension(media_type) or ".bin"
    target_path = output_dir / f"freesound-{source_id}-{time.time_ns()}{suffix}"
    target_path.write_bytes(response.content)

    return FreesoundOriginalDownload(
        path=target_path,
        filename=filename,
        media_type=media_type,
    )


async def _request_token(
    settings: Settings,
    data: dict[str, str],
    *,
    fallback_refresh_token: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> FreesoundTokenPayload:
    async with httpx.AsyncClient(
        base_url=settings.freesound_base_url,
        timeout=15,
        transport=transport,
        follow_redirects=True,
    ) as client:
        response = await client.post("/apiv2/oauth2/access_token/", data=data)
        response.raise_for_status()
        payload = response.json()

    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or fallback_refresh_token or "")
    if not access_token or not refresh_token:
        raise httpx.HTTPError("Freesound OAuth token response did not include required tokens.")

    expires_in = int(payload.get("expires_in") or 86400)
    expires_at = int(time.time() + max(60, expires_in - 60))
    return FreesoundTokenPayload(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
    )


def _content_disposition_filename(value: str) -> str:
    if not value:
        return ""
    message = Message()
    message["content-disposition"] = value
    return message.get_filename() or ""
