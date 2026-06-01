from __future__ import annotations

import asyncio
import base64
import hmac
import json
import re
import time
import zipfile
from hashlib import sha256
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from backend.app.config import Settings, get_settings
from backend.app.db import (
    DEFAULT_WORKSPACE_ID,
    FreesoundOAuthToken,
    create_saved_folder,
    delete_freesound_oauth_token,
    delete_saved_folder,
    delete_saved_sound,
    feedback_adjustment,
    get_analysis,
    get_freesound_oauth_token,
    initialize_db,
    list_saved_folders,
    list_saved_sounds,
    rename_saved_folder,
    save_analysis,
    save_feedback,
    save_freesound_oauth_token,
    save_sound,
    update_saved_sound,
)
from backend.app.freesound_client import FreesoundClient, FreesoundConfigurationError
from backend.app.freesound_oauth import (
    FreesoundOAuthConfigurationError,
    FreesoundTokenPayload,
    download_freesound_original,
    exchange_authorization_code,
    fetch_freesound_me,
    freesound_authorize_url,
    refresh_access_token,
)
from backend.app.jamendo_client import JamendoClient, JamendoConfigurationError
from backend.app.openverse_client import OpenverseClient
from backend.app.preview_cache import PreviewCacheError, cache_preview_audio, media_type_for_path
from backend.app.prompt_parser import PromptSuggestion, build_search_suggestions, parse_prompt
from backend.app.ranker import score_sound, sort_ranked
from backend.app.schemas import (
    FeedbackRequest,
    FeedbackResponse,
    FreesoundAuthStatus,
    FreesoundOAuthExchangeRequest,
    FreesoundOAuthStartResponse,
    HealthResponse,
    PreviewCacheResponse,
    ProviderStatus,
    ProviderStatusResponse,
    SavedFolder,
    SavedFolderCreate,
    SavedFolderUpdate,
    SavedSound,
    SavedSoundUpdate,
    SearchRequest,
    SearchResponse,
    SearchSuggestion,
    SearchSuggestionsResponse,
    SoundAnalysis,
    SoundSearchResult,
)
from backend.app.source_identity import provider_priority, source_key


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or get_settings()
    initialize_db(active_settings.database_path)

    app = FastAPI(title="SoundScrapper Sound Scout", version="0.1.0")
    app.state.settings = active_settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if active_settings.frontend_dir.exists():
        app.mount(
            "/static",
            StaticFiles(directory=active_settings.frontend_dir),
            name="static",
        )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/provider-status", response_model=ProviderStatusResponse)
    def provider_status(fastapi_request: Request) -> ProviderStatusResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        openverse_has_credentials = bool(
            request_settings.openverse_client_id
            and request_settings.openverse_client_secret
        )
        return ProviderStatusResponse(
            providers=[
                ProviderStatus(
                    provider="freesound",
                    configured=bool(request_settings.freesound_api_key),
                    enabled=bool(request_settings.freesound_api_key),
                    message="키 인식됨"
                    if request_settings.freesound_api_key
                    else "FREESOUND_API_KEY 없음",
                    base_url=request_settings.freesound_base_url,
                ),
                ProviderStatus(
                    provider="jamendo",
                    configured=bool(request_settings.jamendo_client_id),
                    enabled=bool(request_settings.jamendo_client_id),
                    message="CLIENT_ID 인식됨"
                    if request_settings.jamendo_client_id
                    else "JAMENDO_CLIENT_ID 없음",
                    base_url=request_settings.jamendo_base_url,
                ),
                ProviderStatus(
                    provider="openverse",
                    configured=openverse_has_credentials,
                    enabled=True,
                    message="Client credentials 인식됨"
                    if openverse_has_credentials
                    else "인증 정보 없음: 익명 요청 시도",
                    base_url=request_settings.openverse_base_url,
                ),
            ]
        )

    @app.get("/api/search-suggestions", response_model=SearchSuggestionsResponse)
    def search_suggestions(prompt: str = "") -> SearchSuggestionsResponse:
        return SearchSuggestionsResponse(
            suggestions=_search_suggestion_models(
                build_search_suggestions(prompt, limit=4)
            )
        )

    @app.get("/api/freesound/auth-status", response_model=FreesoundAuthStatus)
    async def freesound_auth_status(fastapi_request: Request) -> FreesoundAuthStatus:
        request_settings: Settings = fastapi_request.app.state.settings
        if not _freesound_oauth_configured(request_settings):
            return FreesoundAuthStatus(
                configured=False,
                logged_in=False,
                message="Freesound OAuth client is not configured.",
            )

        workspace_id = _workspace_id(fastapi_request)
        token = await _valid_freesound_token(request_settings, workspace_id)
        if token is None:
            return FreesoundAuthStatus(
                configured=True,
                logged_in=False,
                message="Freesound login is required for original downloads.",
            )
        return FreesoundAuthStatus(
            configured=True,
            logged_in=True,
            username=token.username or None,
            expires_at=token.expires_at,
            message="Freesound OAuth is connected.",
        )

    @app.get("/api/freesound/oauth/start", response_model=FreesoundOAuthStartResponse)
    def start_freesound_oauth(fastapi_request: Request) -> FreesoundOAuthStartResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            state = _make_freesound_oauth_state(
                request_settings,
                _workspace_id(fastapi_request),
            )
            authorize_url = freesound_authorize_url(request_settings, state)
        except FreesoundOAuthConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return FreesoundOAuthStartResponse(authorize_url=authorize_url)

    @app.get("/api/freesound/oauth/callback", include_in_schema=False)
    async def freesound_oauth_callback(
        fastapi_request: Request,
        code: str | None = None,
        state: str | None = None,
        error: str | None = None,
    ) -> RedirectResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        if error:
            return RedirectResponse(url="/?freesound_login=denied")
        if not code or not state:
            return RedirectResponse(url="/?freesound_login=missing")

        try:
            workspace_id = _workspace_id_from_oauth_state(request_settings, state)
            payload = await exchange_authorization_code(request_settings, code)
            await _save_freesound_token_from_payload(request_settings, workspace_id, payload)
        except (FreesoundOAuthConfigurationError, ValueError, httpx.HTTPError):
            return RedirectResponse(url="/?freesound_login=failed")
        return RedirectResponse(url="/?freesound_login=success")

    @app.post("/api/freesound/oauth/exchange", response_model=FreesoundAuthStatus)
    async def exchange_freesound_oauth_code(
        exchange: FreesoundOAuthExchangeRequest,
        fastapi_request: Request,
    ) -> FreesoundAuthStatus:
        request_settings: Settings = fastapi_request.app.state.settings
        workspace_id = _workspace_id(fastapi_request)
        try:
            payload = await exchange_authorization_code(request_settings, exchange.code)
            token = await _save_freesound_token_from_payload(
                request_settings,
                workspace_id,
                payload,
            )
        except FreesoundOAuthConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Freesound OAuth failed: {exc}") from exc

        return FreesoundAuthStatus(
            configured=True,
            logged_in=True,
            username=token.username or None,
            expires_at=token.expires_at,
            message="Freesound OAuth is connected.",
        )

    @app.post("/api/freesound/logout", status_code=204)
    def logout_freesound(fastapi_request: Request) -> None:
        request_settings: Settings = fastapi_request.app.state.settings
        delete_freesound_oauth_token(
            request_settings.database_path,
            workspace_id=_workspace_id(fastapi_request),
        )

    @app.get("/api/freesound/original-download/{source_id}")
    async def download_freesound_original_sound(
        source_id: str,
        fastapi_request: Request,
        name: str = "sound",
        workspace_id: str | None = None,
        prefer_name: bool = False,
    ) -> FileResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        active_workspace_id = _workspace_id_from_value(
            workspace_id or fastapi_request.headers.get("X-SoundScrapper-Workspace", "")
        )
        token = await _valid_freesound_token(request_settings, active_workspace_id)
        if token is None:
            raise HTTPException(status_code=401, detail="Freesound login is required.")

        try:
            download = await download_freesound_original(
                request_settings,
                source_id,
                token.access_token,
                name,
            )
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Freesound original download failed: {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Freesound original download failed: {exc}",
            ) from exc

        return FileResponse(
            download.path,
            media_type=download.media_type,
            filename=_safe_download_filename(
                name if prefer_name else download.filename or name,
                source_id,
                download.path.suffix,
                preserve_extension=True,
            ),
            background=BackgroundTask(download.path.unlink, missing_ok=True),
        )

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = active_settings.frontend_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend index.html was not found.")
        return FileResponse(index_path)

    @app.post("/api/search", response_model=SearchResponse)
    async def search_sounds(request: SearchRequest, fastapi_request: Request) -> SearchResponse:
        if request.max_duration < request.min_duration:
            raise HTTPException(
                status_code=422,
                detail="max_duration must be greater than or equal to min_duration.",
            )

        parsed = parse_prompt(request.prompt)
        raw_results, source_warnings = await _search_sources(
            active_settings,
            request,
            parsed.query,
        )

        ranked: list[tuple[SoundSearchResult, SoundAnalysis | None]] = []
        for result in raw_results:
            analysis = (
                get_analysis(active_settings.database_path, result.id)
                if request.game_ready
                else None
            )
            ranked_result = score_sound(
                result=result,
                parsed_prompt=parsed,
                min_duration=request.min_duration,
                max_duration=request.max_duration,
                game_ready=request.game_ready,
                search_modes=request.search_modes,
                analysis=analysis,
            )
            ranked.append((ranked_result, analysis))

        adjusted = []
        for result, analysis in ranked:
            adjustment = feedback_adjustment(
                active_settings.database_path,
                result,
                analysis=analysis,
                workspace_id=_workspace_id(fastapi_request),
            )
            reasons = list(result.score_reasons)
            if adjustment > 0:
                reasons.append(f"사용자 평가 반영 +{adjustment}")
            elif adjustment < 0:
                reasons.append(f"사용자 평가 반영 {adjustment}")
            if hasattr(result, "model_copy"):
                result = result.model_copy(
                    update={
                        "score": max(0, min(100, result.score + adjustment)),
                        "personal_score_adjustment": adjustment,
                        "score_reasons": reasons,
                    }
                )
            else:
                result = result.copy(
                    update={
                        "score": max(0, min(100, result.score + adjustment)),
                        "personal_score_adjustment": adjustment,
                        "score_reasons": reasons,
                    }
                )
            adjusted.append(result)

        sorted_results = sort_ranked(adjusted)
        suggested_queries = (
            _search_suggestion_models(build_search_suggestions(parsed, limit=3))
            if len(sorted_results) <= 5
            else []
        )

        return SearchResponse(
            query=parsed.query,
            results=sorted_results,
            source_warnings=source_warnings,
            interpreted_concepts=list(parsed.interpreted_concepts),
            negative_concepts=list(parsed.negative_concepts),
            suggested_queries=suggested_queries,
        )

    @app.post("/api/saved-sounds", response_model=SavedSound)
    def create_saved_sound(sound: SoundSearchResult, fastapi_request: Request) -> SavedSound:
        request_settings: Settings = fastapi_request.app.state.settings
        return save_sound(
            request_settings.database_path,
            sound,
            workspace_id=_workspace_id(fastapi_request),
        )

    @app.get("/api/saved-sounds", response_model=list[SavedSound])
    def get_saved_sounds(fastapi_request: Request) -> list[SavedSound]:
        request_settings: Settings = fastapi_request.app.state.settings
        return list_saved_sounds(
            request_settings.database_path,
            workspace_id=_workspace_id(fastapi_request),
        )

    @app.patch("/api/saved-sounds/{saved_id}", response_model=SavedSound)
    def patch_saved_sound(
        saved_id: int,
        update: SavedSoundUpdate,
        fastapi_request: Request,
    ) -> SavedSound:
        request_settings: Settings = fastapi_request.app.state.settings
        saved = update_saved_sound(
            request_settings.database_path,
            saved_id,
            update,
            workspace_id=_workspace_id(fastapi_request),
        )
        if saved is None:
            raise HTTPException(status_code=404, detail="Saved sound was not found.")
        return saved

    @app.delete("/api/saved-sounds/{saved_id}", status_code=204)
    def remove_saved_sound(saved_id: int, fastapi_request: Request) -> None:
        request_settings: Settings = fastapi_request.app.state.settings
        deleted = delete_saved_sound(
            request_settings.database_path,
            saved_id,
            workspace_id=_workspace_id(fastapi_request),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved sound was not found.")

    @app.get("/api/saved-folders", response_model=list[SavedFolder])
    def get_saved_folders(fastapi_request: Request) -> list[SavedFolder]:
        request_settings: Settings = fastapi_request.app.state.settings
        return list_saved_folders(
            request_settings.database_path,
            workspace_id=_workspace_id(fastapi_request),
        )

    @app.post("/api/saved-folders", response_model=SavedFolder)
    def post_saved_folder(
        folder: SavedFolderCreate,
        fastapi_request: Request,
    ) -> SavedFolder:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            return create_saved_folder(
                request_settings.database_path,
                folder.name,
                workspace_id=_workspace_id(fastapi_request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.patch("/api/saved-folders/{folder_id}", response_model=SavedFolder)
    def patch_saved_folder(
        folder_id: int,
        folder: SavedFolderUpdate,
        fastapi_request: Request,
    ) -> SavedFolder:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            updated = rename_saved_folder(
                request_settings.database_path,
                folder_id,
                folder.name,
                workspace_id=_workspace_id(fastapi_request),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if updated is None:
            raise HTTPException(status_code=404, detail="Saved folder was not found.")
        return updated

    @app.delete("/api/saved-folders/{folder_id}", status_code=204)
    def remove_saved_folder(folder_id: int, fastapi_request: Request) -> None:
        request_settings: Settings = fastapi_request.app.state.settings
        deleted = delete_saved_folder(
            request_settings.database_path,
            folder_id,
            workspace_id=_workspace_id(fastapi_request),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Saved folder was not found.")

    @app.get("/api/saved-folders/{folder_id}/download")
    async def download_saved_folder(
        folder_id: int,
        fastapi_request: Request,
        saved_ids: str | None = None,
        prefer_original: bool = True,
        allow_preview_fallback: bool = True,
    ) -> FileResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        workspace_id = _workspace_id(fastapi_request)
        folder_name = _folder_name_for_download(
            request_settings.database_path,
            folder_id,
            workspace_id,
        )
        if folder_name is None:
            raise HTTPException(status_code=404, detail="Saved folder was not found.")

        archive_path = await _build_saved_folder_archive(
            request_settings,
            folder_id,
            folder_name,
            saved_ids,
            workspace_id,
            prefer_original=prefer_original,
            allow_preview_fallback=allow_preview_fallback,
        )
        return FileResponse(
            archive_path,
            media_type="application/zip",
            filename=_safe_download_filename(folder_name or "미분류", folder_id, ".zip"),
            background=BackgroundTask(archive_path.unlink, missing_ok=True),
        )

    @app.get("/api/preview-audio/{sound_id}")
    async def get_preview_audio(sound_id: int, preview_url: str, fastapi_request: Request) -> FileResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            path = await cache_preview_audio(
                request_settings.preview_cache_dir,
                sound_id,
                preview_url,
            )
        except PreviewCacheError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Preview download failed: {exc}") from exc

        return FileResponse(path, media_type=media_type_for_path(path))

    @app.get("/api/download-preview/{sound_id}")
    async def download_preview_audio(
        sound_id: int,
        preview_url: str,
        fastapi_request: Request,
        name: str = "sound",
        preserve_name_extension: bool = False,
    ) -> FileResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            path = await cache_preview_audio(
                request_settings.preview_cache_dir,
                sound_id,
                preview_url,
            )
        except PreviewCacheError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Preview download failed: {exc}") from exc

        return FileResponse(
            path,
            media_type=media_type_for_path(path),
            filename=_safe_download_filename(
                name,
                sound_id,
                path.suffix,
                preserve_extension=preserve_name_extension,
            ),
        )

    @app.post("/api/preview-cache/{sound_id}", response_model=PreviewCacheResponse)
    async def create_preview_cache(
        sound_id: int,
        preview_url: str,
        fastapi_request: Request,
    ) -> PreviewCacheResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        try:
            await cache_preview_audio(request_settings.preview_cache_dir, sound_id, preview_url)
        except PreviewCacheError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Preview download failed: {exc}") from exc

        return PreviewCacheResponse(
            id=sound_id,
            audio_url=f"/api/preview-audio/{sound_id}?preview_url={quote(preview_url, safe='')}",
        )

    @app.post("/api/sound-analyses", response_model=SoundAnalysis)
    def create_sound_analysis(analysis: SoundAnalysis, fastapi_request: Request) -> SoundAnalysis:
        request_settings: Settings = fastapi_request.app.state.settings
        return save_analysis(request_settings.database_path, analysis)

    @app.get("/api/sound-analyses/{sound_id}", response_model=SoundAnalysis | None)
    def read_sound_analysis(sound_id: int, fastapi_request: Request) -> SoundAnalysis | None:
        request_settings: Settings = fastapi_request.app.state.settings
        return get_analysis(request_settings.database_path, sound_id)

    @app.post("/api/feedback", response_model=FeedbackResponse)
    def create_feedback(feedback: FeedbackRequest, fastapi_request: Request) -> FeedbackResponse:
        request_settings: Settings = fastapi_request.app.state.settings
        return save_feedback(
            request_settings.database_path,
            feedback,
            workspace_id=_workspace_id(fastapi_request),
        )

    return app


app = create_app()


def _search_suggestion_models(
    suggestions: tuple[PromptSuggestion, ...],
) -> list[SearchSuggestion]:
    return [
        SearchSuggestion(
            label=suggestion.label,
            prompt=suggestion.prompt,
            reason=suggestion.reason,
        )
        for suggestion in suggestions
    ]


async def _search_sources(
    settings: Settings,
    request: SearchRequest,
    query: str,
) -> tuple[list[SoundSearchResult], list[str]]:
    tasks = []
    warnings = []
    sources = _requested_sources(request.source_filter)

    if "freesound" in sources:
        if settings.freesound_api_key:
            tasks.append(
                (
                    "Freesound",
                    0,
                    FreesoundClient(
                        api_key=settings.freesound_api_key,
                        base_url=settings.freesound_base_url,
                    ).search(
                        query=query,
                        license_filter=request.license,
                        min_duration=request.min_duration,
                        max_duration=request.max_duration,
                        page_size=request.page_size,
                    ),
                )
            )
        else:
            warnings.append("Freesound API 키가 없어 Freesound 검색을 건너뜁니다.")

    if "jamendo" in sources:
        if settings.jamendo_client_id:
            tasks.append(
                (
                    "Jamendo",
                    1,
                    JamendoClient(
                        client_id=settings.jamendo_client_id,
                        base_url=settings.jamendo_base_url,
                    ).search(
                        query=query,
                        license_filter=request.license,
                        min_duration=request.min_duration,
                        max_duration=request.max_duration,
                        page_size=request.page_size,
                    ),
                )
            )
        else:
            warnings.append("Jamendo CLIENT_ID가 없어 Jamendo 검색을 건너뜁니다.")

    if "openverse" in sources:
        tasks.append(
            (
                "Openverse",
                2,
                OpenverseClient(
                    client_id=settings.openverse_client_id,
                    client_secret=settings.openverse_client_secret,
                    base_url=settings.openverse_base_url,
                ).search(
                    query=query,
                    license_filter=request.license,
                    min_duration=request.min_duration,
                    max_duration=request.max_duration,
                    page_size=request.page_size,
                ),
            )
        )

    collected = []
    if tasks:
        results = await asyncio.gather(
            *[_source_result(name, priority, task) for name, priority, task in tasks]
        )
        for source_results, source_warning in results:
            collected.extend(source_results)
            if source_warning:
                warnings.append(source_warning)

    return _dedupe_results(collected), warnings


async def _source_result(
    name: str,
    priority: int,
    task,
) -> tuple[list[SoundSearchResult], str | None]:
    try:
        results = await task
        return [_with_provider_priority(result, priority) for result in results], None
    except FreesoundConfigurationError as exc:
        return [], str(exc)
    except JamendoConfigurationError as exc:
        return [], str(exc)
    except httpx.HTTPStatusError as exc:
        return [], f"{name} API 오류: {exc.response.status_code}"
    except httpx.HTTPError as exc:
        return [], f"{name} 요청 실패: {exc}"


def _requested_sources(source_filter: str) -> set[str]:
    if source_filter == "all":
        return {"freesound", "jamendo", "openverse"}
    return {source_filter}


def _with_provider_priority(result: SoundSearchResult, priority: int) -> SoundSearchResult:
    if hasattr(result, "model_copy"):
        return result.model_copy(update={"score_reasons": [*result.score_reasons]})
    return result.copy(update={"score_reasons": [*result.score_reasons]})


def _dedupe_results(results: list[SoundSearchResult]) -> list[SoundSearchResult]:
    best: dict[tuple[str, str], tuple[int, int, SoundSearchResult]] = {}
    for order, result in enumerate(results):
        key = source_key(result.source_provider, result.source_id or result.id)
        priority = provider_priority(result.source_provider)
        previous = best.get(key)
        if previous is None or (priority, order) < (previous[0], previous[1]):
            best[key] = (priority, order, result)

    return [item[2] for item in sorted(best.values(), key=lambda value: value[1])]


def _workspace_id(request: Request) -> str:
    raw = request.headers.get("X-SoundScrapper-Workspace", DEFAULT_WORKSPACE_ID)
    return _workspace_id_from_value(raw)


def _workspace_id_from_value(value: str) -> str:
    normalized = "".join(
        character for character in str(value or "").strip() if character.isalnum() or character in "._-"
    )
    return normalized[:80] or DEFAULT_WORKSPACE_ID


def _freesound_oauth_configured(settings: Settings) -> bool:
    return bool(settings.freesound_client_id and settings.freesound_client_secret)


def _make_freesound_oauth_state(settings: Settings, workspace_id: str) -> str:
    if not settings.freesound_client_secret:
        raise FreesoundOAuthConfigurationError("FREESOUND_CLIENT_SECRET is required.")
    workspace_id = _workspace_id_from_value(workspace_id)
    payload = {
        "workspace_id": workspace_id,
        "ts": int(time.time()),
    }
    encoded_payload = _urlsafe_json(payload)
    signature = hmac.new(
        settings.freesound_client_secret.encode(),
        encoded_payload.encode(),
        sha256,
    ).digest()
    return f"{encoded_payload}.{_urlsafe_bytes(signature)}"


def _workspace_id_from_oauth_state(settings: Settings, state: str) -> str:
    if not settings.freesound_client_secret:
        raise FreesoundOAuthConfigurationError("FREESOUND_CLIENT_SECRET is required.")
    try:
        encoded_payload, encoded_signature = state.split(".", 1)
        expected_signature = hmac.new(
            settings.freesound_client_secret.encode(),
            encoded_payload.encode(),
            sha256,
        ).digest()
        actual_signature = _unurlsafe_bytes(encoded_signature)
        if not hmac.compare_digest(expected_signature, actual_signature):
            raise ValueError("Invalid Freesound OAuth state signature.")
        payload = json.loads(_unurlsafe_bytes(encoded_payload).decode())
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Freesound OAuth state.") from exc

    if int(time.time()) - int(payload.get("ts") or 0) > 600:
        raise ValueError("Freesound OAuth state expired.")
    return _workspace_id_from_value(payload.get("workspace_id") or "")


async def _save_freesound_token_from_payload(
    settings: Settings,
    workspace_id: str,
    payload: FreesoundTokenPayload,
) -> FreesoundOAuthToken:
    username = ""
    try:
        profile = await fetch_freesound_me(settings, payload.access_token)
        username = str(profile.get("username") or "")
    except httpx.HTTPError:
        username = ""

    return save_freesound_oauth_token(
        settings.database_path,
        FreesoundOAuthToken(
            workspace_id=workspace_id,
            access_token=payload.access_token,
            refresh_token=payload.refresh_token,
            expires_at=payload.expires_at,
            username=username,
        ),
    )


async def _valid_freesound_token(
    settings: Settings,
    workspace_id: str,
) -> FreesoundOAuthToken | None:
    if not _freesound_oauth_configured(settings):
        return None
    token = get_freesound_oauth_token(settings.database_path, workspace_id=workspace_id)
    if token is None:
        return None
    if token.expires_at > int(time.time()) + 60:
        return token

    try:
        payload = await refresh_access_token(settings, token.refresh_token)
        return save_freesound_oauth_token(
            settings.database_path,
            FreesoundOAuthToken(
                workspace_id=workspace_id,
                access_token=payload.access_token,
                refresh_token=payload.refresh_token,
                expires_at=payload.expires_at,
                username=token.username,
            ),
        )
    except httpx.HTTPError:
        delete_freesound_oauth_token(settings.database_path, workspace_id=workspace_id)
        return None


def _urlsafe_json(payload: dict[str, object]) -> str:
    return _urlsafe_bytes(json.dumps(payload, separators=(",", ":")).encode())


def _urlsafe_bytes(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unurlsafe_bytes(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _folder_name_for_download(database_path, folder_id: int, workspace_id: str) -> str | None:
    if folder_id == 0:
        return ""
    for folder in list_saved_folders(database_path, workspace_id=workspace_id):
        if folder.folder_id == folder_id:
            return folder.name
    return None


async def _build_saved_folder_archive(
    settings: Settings,
    folder_id: int,
    folder_name: str,
    saved_ids: str | None = None,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    *,
    prefer_original: bool = True,
    allow_preview_fallback: bool = True,
):
    folder_label = folder_name or "미분류"
    saved_sounds = [
        sound
        for sound in list_saved_sounds(settings.database_path, workspace_id=workspace_id)
        if (sound.folder or "").strip() == folder_name
    ]
    saved_sounds = _apply_saved_id_order(saved_sounds, saved_ids)
    archive_dir = settings.preview_cache_dir / "folder-downloads"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"saved-folder-{folder_id}-{time.time_ns()}.zip"
    freesound_token = (
        await _valid_freesound_token(settings, workspace_id)
        if prefer_original
        else None
    )

    used_names: set[str] = set()
    added = 0
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, sound in enumerate(saved_sounds):
            default_name = f"{folder_label}_{index + 1}"
            base_name = (sound.download_filename or "").strip() or default_name
            if (
                sound.source_provider == "freesound"
                and freesound_token
                and sound.source_id
            ):
                try:
                    download = await download_freesound_original(
                        settings,
                        sound.source_id,
                        freesound_token.access_token,
                        sound.name,
                    )
                except httpx.HTTPError as exc:
                    if not allow_preview_fallback:
                        raise HTTPException(
                            status_code=502,
                            detail=f"Freesound original download failed: {exc}",
                        ) from exc
                else:
                    archive_name = _dedupe_archive_filename(
                        _safe_download_filename(base_name, sound.id, download.path.suffix),
                        used_names,
                    )
                    archive.write(download.path, archive_name)
                    download.path.unlink(missing_ok=True)
                    added += 1
                    continue

            preview_url = sound.download_url or sound.preview_url
            if not sound.download_allowed or not preview_url:
                continue
            try:
                path = await cache_preview_audio(
                    settings.preview_cache_dir,
                    sound.id,
                    preview_url,
                )
            except PreviewCacheError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            except httpx.HTTPError as exc:
                raise HTTPException(status_code=502, detail=f"Preview download failed: {exc}") from exc

            archive_name = _dedupe_archive_filename(
                _safe_download_filename(base_name, sound.id, path.suffix),
                used_names,
            )
            archive.write(path, archive_name)
            added += 1

    if added == 0:
        archive_path.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="No downloadable saved sounds in folder.")

    return archive_path


def _apply_saved_id_order(saved_sounds: list[SavedSound], saved_ids: str | None) -> list[SavedSound]:
    if not saved_ids:
        return saved_sounds
    ordered_ids = []
    for raw_id in saved_ids.split(","):
        try:
            ordered_ids.append(int(raw_id.strip()))
        except ValueError:
            continue
    if not ordered_ids:
        return saved_sounds
    order = {saved_id: index for index, saved_id in enumerate(ordered_ids)}
    return sorted(
        saved_sounds,
        key=lambda sound: (order.get(sound.saved_id, len(order)), sound.saved_id),
    )


def _dedupe_archive_filename(filename: str, used_names: set[str]) -> str:
    if filename not in used_names:
        used_names.add(filename)
        return filename

    stem, dot, suffix = filename.rpartition(".")
    if not dot:
        stem = filename
        suffix = ""
    for index in range(2, 1000):
        candidate = f"{stem}_{index}.{suffix}" if suffix else f"{stem}_{index}"
        if candidate not in used_names:
            used_names.add(candidate)
            return candidate

    candidate = f"{stem}_{time.time_ns()}.{suffix}" if suffix else f"{stem}_{time.time_ns()}"
    used_names.add(candidate)
    return candidate


def _safe_download_filename(
    name: str,
    sound_id: int | str,
    suffix: str,
    *,
    preserve_extension: bool = False,
) -> str:
    base = re.sub(r"[^\w가-힣 ._-]+", "-", name, flags=re.ASCII).strip(" ._-")
    base = re.sub(r"\s+", " ", base)[:80].strip(" ._-")
    if not base:
        base = f"sound-{sound_id}"
    if preserve_extension and re.search(
        r"\.(wav|mp3|ogg|flac|aif|aiff|m4a|opus)$",
        base,
        flags=re.IGNORECASE,
    ):
        return base
    if not suffix.startswith("."):
        suffix = ".mp3"
    if base.lower().endswith(suffix.lower()):
        return base
    return f"{base}{suffix}"
