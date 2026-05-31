from __future__ import annotations

import asyncio
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.db import (
    feedback_adjustment,
    get_analysis,
    list_saved_sounds,
    save_analysis,
    save_feedback,
    save_sound,
)
from backend.app.freesound_client import FreesoundClient, build_filter
from backend.app.main import create_app
from backend.app.prompt_parser import parse_prompt
from backend.app.preview_cache import cache_preview_audio, is_allowed_preview_url
from backend.app.ranker import score_sound
from backend.app.schemas import FeedbackRequest, SoundAnalysis, SoundSearchResult


def test_parse_prompt_expands_korean_keywords() -> None:
    parsed = parse_prompt("짧고 묵직한 암흑 마법 폭발음 게임용")

    assert "explosion" in parsed.query
    assert "magic" in parsed.query
    assert "dark" in parsed.query
    assert "heavy" in parsed.query
    assert "sfx" in parsed.query


def test_ranker_prefers_matching_cc0_sound() -> None:
    parsed = parse_prompt("dark magic impact")
    result = SoundSearchResult(
        id=1,
        name="Dark Magic Impact",
        license="Creative Commons 0",
        duration=0.8,
        tags=["dark", "magic", "impact"],
        preview_url="https://example.com/a.mp3",
    )

    scored = score_sound(result, parsed, min_duration=0.1, max_duration=3.0)

    assert scored.score > 80
    assert any("CC0" in reason for reason in scored.score_reasons)
    assert any("검색어 일치" in reason for reason in scored.score_reasons)


def test_ranker_game_ready_prefers_clean_short_sfx() -> None:
    parsed = parse_prompt("button click")
    clean = SoundSearchResult(
        id=2,
        name="Clean UI Click SFX",
        license="Creative Commons 0",
        duration=0.35,
        tags=["clean", "ui", "click", "sfx"],
        preview_url="https://example.com/click.mp3",
    )
    noisy = SoundSearchResult(
        id=3,
        name="Street ambience field recording",
        license="Creative Commons 0",
        duration=14,
        tags=["ambience", "field-recording", "noise", "traffic"],
        preview_url="https://example.com/noise.mp3",
    )

    clean_scored = score_sound(clean, parsed, min_duration=0.1, max_duration=15, game_ready=True)
    noisy_scored = score_sound(noisy, parsed, min_duration=0.1, max_duration=15, game_ready=True)

    assert clean_scored.score > noisy_scored.score
    assert any("게임용" in reason for reason in clean_scored.score_reasons)
    assert any("환경음/잡음" in reason for reason in noisy_scored.score_reasons)


def test_ranker_game_ready_uses_cached_waveform_analysis() -> None:
    parsed = parse_prompt("magic impact")
    result = SoundSearchResult(
        id=4,
        name="Magic Impact",
        license="Creative Commons 0",
        duration=2,
        tags=["magic", "impact", "sfx"],
        preview_url="https://example.com/magic.mp3",
    )
    analysis = SoundAnalysis(
        id=4,
        preview_url="https://example.com/magic.mp3",
        duration=2,
        waveform=[0, 0.82, 0.7, 0.03, 0.02, 0.9, 0.72, 0.01],
        leading_silence_seconds=0.04,
        emptiness_score=8,
        sharpness_score=40,
    )

    scored = score_sound(
        result,
        parsed,
        min_duration=0.1,
        max_duration=5,
        game_ready=True,
        analysis=analysis,
    )

    assert any("파형 분리 쉬움" in reason for reason in scored.score_reasons)
    assert any("앞 무음 적음" in reason for reason in scored.score_reasons)


def test_db_save_and_list_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "sounds.db"
    sound = SoundSearchResult(
        id=10,
        name="Click",
        username="tester",
        license="Attribution",
        duration=0.3,
        tags=["button", "click"],
        score=72,
    )

    saved = save_sound(database_path, sound)
    listed = list_saved_sounds(database_path)

    assert saved.id == 10
    assert listed[0].name == "Click"
    assert listed[0].tags == ["button", "click"]


def test_api_health_and_saved_sounds(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "api.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}

    response = client.post(
        "/api/saved-sounds",
        json={
            "id": 20,
            "name": "Boom",
            "username": "tester",
            "license": "Creative Commons 0",
            "duration": 1.2,
            "tags": ["boom"],
            "score": 90,
        },
    )

    assert response.status_code == 200
    assert client.get("/api/saved-sounds").json()[0]["id"] == 20


def test_search_without_api_key_returns_503(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "missing-key.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.post("/api/search", json={"prompt": "boom"})

    assert response.status_code == 503
    assert "FREESOUND_API_KEY" in response.json()["detail"]


def test_freesound_client_uses_search_endpoint_and_fields() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/apiv2/search/"
        assert request.headers["Authorization"] == "Token test-token"
        assert "fields=id%2Cname%2Cusername%2Clicense" in str(request.url)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": 99,
                        "name": "Test Boom",
                        "username": "creator",
                        "license": "Creative Commons 0",
                        "duration": 0.7,
                        "tags": ["boom"],
                        "previews": {"preview-hq-mp3": "https://example.com/boom.mp3"},
                        "url": "https://freesound.org/s/99/",
                        "description": "Test sound",
                    }
                ]
            },
        )

    client = FreesoundClient(
        api_key="test-token",
        base_url="https://freesound.test",
        transport=httpx.MockTransport(handler),
    )

    results = asyncio.run(
        client.search(
            query="boom",
            license_filter="commercial",
            min_duration=0.1,
            max_duration=3.0,
            page_size=5,
        )
    )

    assert results[0].id == 99
    assert results[0].preview_url == "https://example.com/boom.mp3"


def test_build_filter_variants() -> None:
    assert 'license:"Creative Commons 0"' in build_filter("cc0", 0.1, 3.0)
    assert 'license:"Attribution"' in build_filter("commercial", 0.1, 3.0)
    assert "license" not in build_filter("any", 0.1, 3.0)


def test_analysis_save_and_get_round_trip(tmp_path: Path) -> None:
    database_path = tmp_path / "analysis.db"
    analysis = SoundAnalysis(
        id=55,
        preview_url="https://cdn.freesound.org/previews/55.mp3",
        waveform=[0.1, 0.5, 1.0],
        duration=1.5,
        rms=0.2,
        peak=0.9,
        leading_silence_seconds=0.25,
        low_ratio=0.5,
        mid_ratio=0.3,
        high_ratio=0.2,
        spectral_centroid_hz=1200,
        heaviness_score=72,
        sharpness_score=31,
        emptiness_score=12,
    )

    saved = save_analysis(database_path, analysis)
    loaded = get_analysis(database_path, 55)

    assert saved.waveform == [0.1, 0.5, 1.0]
    assert loaded is not None
    assert loaded.duration == 1.5
    assert loaded.heaviness_score == 72


def test_feedback_adjusts_related_results(tmp_path: Path) -> None:
    database_path = tmp_path / "feedback.db"
    save_feedback(
        database_path,
        FeedbackRequest(
            id=1,
            prompt="heavy magic",
            feedback_type="heavy_good",
            name="Dark Magic Boom",
            tags=["dark", "magic", "boom"],
        ),
    )

    result = SoundSearchResult(
        id=2,
        name="Magic Boom",
        tags=["magic", "boom"],
    )

    assert feedback_adjustment(database_path, result) > 0


def test_preview_cache_rejects_non_freesound_url(tmp_path: Path) -> None:
    assert is_allowed_preview_url("https://cdn.freesound.org/previews/1.mp3")
    assert not is_allowed_preview_url("http://cdn.freesound.org/previews/1.mp3")
    assert not is_allowed_preview_url("https://example.com/sound.mp3")


def test_preview_cache_downloads_audio(tmp_path: Path) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "cdn.freesound.org"
        return httpx.Response(200, headers={"content-type": "audio/mpeg"}, content=b"audio")

    path = asyncio.run(
        cache_preview_audio(
            tmp_path,
            99,
            "https://cdn.freesound.org/previews/99.mp3",
            transport=httpx.MockTransport(handler),
        )
    )

    assert path.exists()
    assert path.read_bytes() == b"audio"
