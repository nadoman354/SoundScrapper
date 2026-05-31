from __future__ import annotations

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from urllib.parse import quote

from backend.app.config import Settings, get_settings
from backend.app.db import (
    feedback_adjustment,
    get_analysis,
    initialize_db,
    list_saved_sounds,
    save_analysis,
    save_feedback,
    save_sound,
)
from backend.app.freesound_client import FreesoundClient, FreesoundConfigurationError
from backend.app.preview_cache import PreviewCacheError, cache_preview_audio, media_type_for_path
from backend.app.prompt_parser import parse_prompt
from backend.app.ranker import score_sound, sort_ranked
from backend.app.schemas import (
    HealthResponse,
    FeedbackRequest,
    FeedbackResponse,
    PreviewCacheResponse,
    SavedSound,
    SearchRequest,
    SearchResponse,
    SoundAnalysis,
    SoundSearchResult,
)


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

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        index_path = active_settings.frontend_dir / "index.html"
        if not index_path.exists():
            raise HTTPException(status_code=404, detail="Frontend index.html was not found.")
        return FileResponse(index_path)

    @app.post("/api/search", response_model=SearchResponse)
    async def search_sounds(request: SearchRequest) -> SearchResponse:
        if request.max_duration < request.min_duration:
            raise HTTPException(
                status_code=422,
                detail="max_duration must be greater than or equal to min_duration.",
            )

        parsed = parse_prompt(request.prompt)
        client = FreesoundClient(
            api_key=active_settings.freesound_api_key,
            base_url=active_settings.freesound_base_url,
        )

        try:
            raw_results = await client.search(
                query=parsed.query,
                license_filter=request.license,
                min_duration=request.min_duration,
                max_duration=request.max_duration,
                page_size=request.page_size,
            )
        except FreesoundConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(
                status_code=exc.response.status_code,
                detail=f"Freesound API error: {exc.response.text}",
            ) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Freesound request failed: {exc}") from exc

        ranked = [
            score_sound(
                result=result,
                parsed_prompt=parsed,
                min_duration=request.min_duration,
                max_duration=request.max_duration,
                game_ready=request.game_ready,
                analysis=get_analysis(active_settings.database_path, result.id)
                if request.game_ready
                else None,
            )
            for result in raw_results
        ]
        adjusted = []
        for result in ranked:
            adjustment = feedback_adjustment(active_settings.database_path, result)
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

        return SearchResponse(query=parsed.query, results=sort_ranked(adjusted))

    @app.post("/api/saved-sounds", response_model=SavedSound)
    def create_saved_sound(sound: SoundSearchResult, fastapi_request: Request) -> SavedSound:
        request_settings: Settings = fastapi_request.app.state.settings
        return save_sound(request_settings.database_path, sound)

    @app.get("/api/saved-sounds", response_model=list[SavedSound])
    def get_saved_sounds(fastapi_request: Request) -> list[SavedSound]:
        request_settings: Settings = fastapi_request.app.state.settings
        return list_saved_sounds(request_settings.database_path)

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
        return save_feedback(request_settings.database_path, feedback)

    return app


app = create_app()
