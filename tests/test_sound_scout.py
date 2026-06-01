from __future__ import annotations

import asyncio
import io
import sqlite3
import zipfile
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from backend.app.config import Settings, _normalize_openverse_base_url
from backend.app.db import (
    create_saved_folder,
    delete_saved_folder,
    delete_saved_sound,
    feedback_adjustment,
    get_analysis,
    list_saved_folders,
    list_saved_sounds,
    rename_saved_folder,
    save_analysis,
    save_feedback,
    save_sound,
    update_saved_sound,
)
from backend.app.freesound_client import FreesoundClient, build_filter
from backend.app.jamendo_client import JamendoClient
from backend.app.main import _dedupe_results, create_app
from backend.app.openverse_client import OpenverseClient
from backend.app.prompt_parser import parse_prompt
from backend.app.preview_cache import cache_preview_audio, is_allowed_preview_url
from backend.app.ranker import score_sound
from backend.app.schemas import FeedbackRequest, SavedSoundUpdate, SoundAnalysis, SoundSearchResult


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


def test_ranker_search_modes_boost_matching_conditions() -> None:
    parsed = parse_prompt("button click")
    clean_short = SoundSearchResult(
        id=5,
        name="Clean UI Click SFX",
        license="Creative Commons 0",
        duration=0.25,
        tags=["clean", "ui", "click", "sfx"],
        preview_url="https://example.com/click.mp3",
    )

    scored = score_sound(
        clean_short,
        parsed,
        min_duration=0.1,
        max_duration=5,
        search_modes=["clean_source", "short_sfx", "rights_safe"],
    )

    assert any("깨끗한 소스" in reason for reason in scored.score_reasons)
    assert any("짧은 원샷" in reason for reason in scored.score_reasons)
    assert any("저작권 안전" in reason for reason in scored.score_reasons)


def test_ranker_source_weighting_for_sfx_and_bgm() -> None:
    parsed = parse_prompt("loop bgm")
    jamendo_track = SoundSearchResult(
        id=1001,
        name="Adventure Loop",
        license="CC BY",
        duration=90,
        tags=["music", "loop"],
        source_provider="jamendo",
        source_id="1001",
    )

    scored = score_sound(
        jamendo_track,
        parsed,
        min_duration=1,
        max_duration=120,
        search_modes=["loop_bgm", "rights_safe"],
    )

    assert any("Jamendo BGM 후보" in reason for reason in scored.score_reasons)
    assert any("저작자 표시 라이선스" in reason for reason in scored.score_reasons)


def test_ranker_search_modes_penalize_conflicting_audio() -> None:
    parsed = parse_prompt("bgm loop")
    tiny_sfx = SoundSearchResult(
        id=6,
        name="Tiny Explosion SFX",
        license="Attribution",
        duration=0.4,
        tags=["explosion", "sfx"],
        preview_url="https://example.com/explosion.mp3",
    )

    scored = score_sound(
        tiny_sfx,
        parsed,
        min_duration=0.1,
        max_duration=10,
        search_modes=["loop_bgm"],
    )

    assert any("루프/BGM으로는 짧음" in reason for reason in scored.score_reasons)
    assert any("짧은 SFX 단서" in reason for reason in scored.score_reasons)


def test_ranker_easy_cut_mode_uses_waveform_analysis() -> None:
    parsed = parse_prompt("impact")
    result = SoundSearchResult(
        id=7,
        name="Separated Impact",
        license="Creative Commons 0",
        duration=2,
        tags=["impact"],
        preview_url="https://example.com/impact.mp3",
    )
    analysis = SoundAnalysis(
        id=7,
        preview_url="https://example.com/impact.mp3",
        duration=2,
        waveform=[0, 0.8, 0.7, 0.02, 0.01, 0.82, 0.65, 0.01],
        leading_silence_seconds=0.05,
    )

    scored = score_sound(
        result,
        parsed,
        min_duration=0.1,
        max_duration=5,
        search_modes=["easy_cut"],
        analysis=analysis,
    )

    assert any("파형 이벤트 분리" in reason for reason in scored.score_reasons)


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
    assert listed[0].source_provider == "freesound"
    assert listed[0].source_id == "10"


def test_saved_sound_metadata_can_be_updated_and_preserved(tmp_path: Path) -> None:
    database_path = tmp_path / "saved-metadata.db"
    sound = SoundSearchResult(
        id=12,
        name="Magic Hit",
        username="tester",
        license="Creative Commons 0",
        duration=0.8,
        tags=["magic", "hit"],
        score=76,
        source_provider="freesound",
        source_id="12",
    )

    saved = save_sound(database_path, sound)
    updated = update_saved_sound(
        database_path,
        saved.saved_id,
        SavedSoundUpdate(
            note="전투 히트 후보",
            fit_rating=4,
            folder="전투",
            labels=["magic", "impact", "magic"],
            download_filename="전투_1",
        ),
    )

    assert updated is not None
    assert updated.note == "전투 히트 후보"
    assert updated.fit_rating == 4
    assert updated.folder == "전투"
    assert updated.labels == ["magic", "impact"]
    assert updated.download_filename == "전투_1"

    sound_data = sound.model_dump() if hasattr(sound, "model_dump") else sound.dict()
    save_sound(database_path, SoundSearchResult(**{**sound_data, "score": 91}))
    listed = list_saved_sounds(database_path)

    assert listed[0].score == 91
    assert listed[0].note == "전투 히트 후보"
    assert listed[0].fit_rating == 4
    assert listed[0].folder == "전투"
    assert listed[0].labels == ["magic", "impact"]
    assert listed[0].download_filename == "전투_1"


def test_saved_folders_rename_and_delete_move_sounds_safely(tmp_path: Path) -> None:
    database_path = tmp_path / "saved-folders.db"
    folder = create_saved_folder(database_path, "UI")
    saved = save_sound(database_path, SoundSearchResult(id=121, name="Click"))
    updated = update_saved_sound(
        database_path,
        saved.saved_id,
        SavedSoundUpdate(folder="UI"),
    )

    assert updated is not None
    assert updated.folder == "UI"
    assert list_saved_folders(database_path)[0].name == "UI"

    renamed = rename_saved_folder(database_path, folder.folder_id, "Menus")
    listed = list_saved_sounds(database_path)

    assert renamed is not None
    assert renamed.name == "Menus"
    assert listed[0].folder == "Menus"

    assert delete_saved_folder(database_path, renamed.folder_id) is True
    listed_after_delete = list_saved_sounds(database_path)

    assert listed_after_delete[0].name == "Click"
    assert listed_after_delete[0].folder == ""


def test_saved_sounds_are_scoped_by_workspace(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace-saved.db"
    owner_sound = SoundSearchResult(id=301, name="Owner Click", score=80)
    guest_sound = SoundSearchResult(id=301, name="Guest Click", score=65)

    owner_saved = save_sound(database_path, owner_sound, workspace_id="owner")
    guest_saved = save_sound(database_path, guest_sound, workspace_id="guest")

    assert owner_saved.saved_id != guest_saved.saved_id
    assert [sound.name for sound in list_saved_sounds(database_path, workspace_id="owner")] == [
        "Owner Click"
    ]
    assert [sound.name for sound in list_saved_sounds(database_path, workspace_id="guest")] == [
        "Guest Click"
    ]

    assert (
        update_saved_sound(
            database_path,
            owner_saved.saved_id,
            SavedSoundUpdate(note="wrong workspace"),
            workspace_id="guest",
        )
        is None
    )
    assert delete_saved_sound(database_path, owner_saved.saved_id, workspace_id="guest") is False
    assert delete_saved_sound(database_path, owner_saved.saved_id, workspace_id="owner") is True
    assert list_saved_sounds(database_path, workspace_id="owner") == []
    assert len(list_saved_sounds(database_path, workspace_id="guest")) == 1


def test_saved_folders_are_scoped_by_workspace(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace-folders.db"
    owner_folder = create_saved_folder(database_path, "UI", workspace_id="owner")
    guest_folder = create_saved_folder(database_path, "UI", workspace_id="guest")
    owner_saved = save_sound(database_path, SoundSearchResult(id=401, name="Owner"), "owner")
    guest_saved = save_sound(database_path, SoundSearchResult(id=402, name="Guest"), "guest")

    update_saved_sound(
        database_path,
        owner_saved.saved_id,
        SavedSoundUpdate(folder="UI"),
        workspace_id="owner",
    )
    update_saved_sound(
        database_path,
        guest_saved.saved_id,
        SavedSoundUpdate(folder="UI"),
        workspace_id="guest",
    )

    assert owner_folder.folder_id != guest_folder.folder_id
    assert list_saved_folders(database_path, workspace_id="owner")[0].sound_count == 1
    assert list_saved_folders(database_path, workspace_id="guest")[0].sound_count == 1

    assert rename_saved_folder(database_path, owner_folder.folder_id, "Menus", "guest") is None
    renamed = rename_saved_folder(database_path, owner_folder.folder_id, "Menus", "owner")
    assert renamed is not None
    assert renamed.name == "Menus"
    assert list_saved_sounds(database_path, workspace_id="owner")[0].folder == "Menus"
    assert list_saved_sounds(database_path, workspace_id="guest")[0].folder == "UI"

    assert delete_saved_folder(database_path, renamed.folder_id, workspace_id="guest") is False
    assert delete_saved_folder(database_path, renamed.folder_id, workspace_id="owner") is True
    assert list_saved_sounds(database_path, workspace_id="owner")[0].folder == ""
    assert list_saved_sounds(database_path, workspace_id="guest")[0].folder == "UI"


def test_feedback_adjustment_is_scoped_by_workspace(tmp_path: Path) -> None:
    database_path = tmp_path / "workspace-feedback.db"
    sound = SoundSearchResult(id=501, name="Clean Sword", tags=["sword"], score=75)
    feedback = FeedbackRequest(
        id=501,
        prompt="sword",
        feedback_type="good",
        name="Clean Sword",
        tags=["sword"],
    )

    save_feedback(database_path, feedback, workspace_id="owner")

    assert feedback_adjustment(database_path, sound, workspace_id="owner") > 0
    assert feedback_adjustment(database_path, sound, workspace_id="guest") == 0


def test_delete_saved_sound_removes_only_saved_candidate(tmp_path: Path) -> None:
    database_path = tmp_path / "delete-saved.db"
    first = save_sound(database_path, SoundSearchResult(id=13, name="Keep"))
    second = save_sound(database_path, SoundSearchResult(id=14, name="Remove"))

    assert delete_saved_sound(database_path, second.saved_id) is True
    assert delete_saved_sound(database_path, second.saved_id) is False

    listed = list_saved_sounds(database_path)
    assert [sound.saved_id for sound in listed] == [first.saved_id]


def test_saved_sounds_include_feedback_types(tmp_path: Path) -> None:
    database_path = tmp_path / "saved-feedback.db"
    sound = SoundSearchResult(
        id=11,
        name="Good Click",
        username="tester",
        license="Creative Commons 0",
        duration=0.2,
        tags=["ui", "click"],
        score=88,
    )

    save_sound(database_path, sound)
    save_feedback(
        database_path,
        FeedbackRequest(
            id=11,
            prompt="ui click",
            feedback_type="good",
            name="Good Click",
            tags=["ui", "click"],
        ),
    )

    listed = list_saved_sounds(database_path)

    assert listed[0].feedback_types == ["good"]


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


def test_api_saved_sounds_are_scoped_by_workspace_header(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "api-workspace.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)
    owner_headers = {"X-SoundScrapper-Workspace": "owner"}
    guest_headers = {"X-SoundScrapper-Workspace": "guest"}

    response = client.post(
        "/api/saved-sounds",
        headers=owner_headers,
        json={
            "id": 33,
            "name": "Private Hit",
            "license": "Creative Commons 0",
            "duration": 0.4,
            "score": 92,
        },
    )

    assert response.status_code == 200
    assert client.get("/api/saved-sounds", headers=guest_headers).json() == []
    assert client.get("/api/saved-folders", headers=guest_headers).json() == []
    assert client.get("/api/saved-sounds", headers=owner_headers).json()[0]["name"] == "Private Hit"


def test_api_updates_and_deletes_saved_sound_metadata(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "api-metadata.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)

    created = client.post(
        "/api/saved-sounds",
        json={
            "id": 21,
            "name": "Loop Candidate",
            "license": "CC BY",
            "duration": 12,
            "score": 68,
            "source_provider": "jamendo",
            "source_id": "track-21",
        },
    ).json()

    response = client.patch(
        f"/api/saved-sounds/{created['saved_id']}",
        json={
            "note": "BGM 루프 후보",
            "fit_rating": 5,
            "folder": "BGM",
            "labels": ["loop", "menu"],
            "download_filename": "BGM_1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["note"] == "BGM 루프 후보"
    assert body["fit_rating"] == 5
    assert body["folder"] == "BGM"
    assert body["labels"] == ["loop", "menu"]
    assert body["download_filename"] == "BGM_1"

    delete_response = client.delete(f"/api/saved-sounds/{created['saved_id']}")

    assert delete_response.status_code == 204
    assert client.get("/api/saved-sounds").json() == []


def test_provider_status_reports_config_without_exposing_secrets(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key="free-secret-value",
        database_path=tmp_path / "provider-status.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
        openverse_client_id="openverse-client-id",
        openverse_client_secret="openverse-secret-value",
        openverse_base_url="https://api.openverse.org",
        jamendo_client_id="jamendo-client-id",
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/provider-status")

    assert response.status_code == 200
    body = response.json()
    providers = {item["provider"]: item for item in body["providers"]}
    assert providers["freesound"]["configured"] is True
    assert providers["jamendo"]["configured"] is True
    assert providers["openverse"]["configured"] is True
    assert providers["openverse"]["base_url"] == "https://api.openverse.org"
    assert "free-secret-value" not in response.text
    assert "openverse-secret-value" not in response.text


def test_openverse_base_url_normalizes_v1_suffix() -> None:
    assert (
        _normalize_openverse_base_url("https://api.openverse.org/v1")
        == "https://api.openverse.org"
    )
    assert (
        _normalize_openverse_base_url("https://api.openverse.org/v1/")
        == "https://api.openverse.org"
    )
    assert (
        _normalize_openverse_base_url("https://api.openverse.org/")
        == "https://api.openverse.org"
    )


def test_download_preview_returns_attachment(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "download.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    preview_path = tmp_path / "previews" / "42.mp3"
    preview_path.parent.mkdir(parents=True)
    preview_path.write_bytes(b"audio")

    async def fake_cache_preview_audio(cache_dir: Path, sound_id: int, preview_url: str) -> Path:
        assert cache_dir == settings.preview_cache_dir
        assert sound_id == 42
        assert preview_url == "https://cdn.freesound.org/previews/42.mp3"
        return preview_path

    monkeypatch.setattr("backend.app.main.cache_preview_audio", fake_cache_preview_audio)
    app = create_app(settings)
    client = TestClient(app)

    response = client.get(
        "/api/download-preview/42",
        params={
            "preview_url": "https://cdn.freesound.org/previews/42.mp3",
            "name": "Big Boom!",
        },
    )

    assert response.status_code == 200
    assert response.content == b"audio"
    assert response.headers["content-type"] == "audio/mpeg"
    assert "attachment" in response.headers["content-disposition"]
    assert "Big%20Boom.mp3" in response.headers["content-disposition"]


def test_saved_folder_download_returns_zip_with_ordered_names(
    tmp_path: Path,
    monkeypatch,
) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "folder-download.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)

    folder = client.post("/api/saved-folders", json={"name": "UI"}).json()
    first = client.post(
        "/api/saved-sounds",
        json={
            "id": 51,
            "name": "Click",
            "preview_url": "https://cdn.freesound.org/previews/51.mp3",
            "download_url": "https://cdn.freesound.org/previews/51.mp3",
            "download_allowed": True,
        },
    ).json()
    second = client.post(
        "/api/saved-sounds",
        json={
            "id": 52,
            "name": "Confirm",
            "preview_url": "https://cdn.freesound.org/previews/52.mp3",
            "download_url": "https://cdn.freesound.org/previews/52.mp3",
            "download_allowed": True,
        },
    ).json()
    client.patch(f"/api/saved-sounds/{first['saved_id']}", json={"folder": "UI"})
    client.patch(f"/api/saved-sounds/{second['saved_id']}", json={"folder": "UI"})

    async def fake_cache_preview_audio(cache_dir: Path, sound_id: int, preview_url: str) -> Path:
        path = cache_dir / f"{sound_id}.mp3"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"audio-{sound_id}".encode())
        return path

    monkeypatch.setattr("backend.app.main.cache_preview_audio", fake_cache_preview_audio)

    response = client.get(f"/api/saved-folders/{folder['folder_id']}/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "attachment" in response.headers["content-disposition"]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert archive.namelist() == ["UI_1.mp3", "UI_2.mp3"]
    assert archive.read("UI_1.mp3") == b"audio-52"
    assert archive.read("UI_2.mp3") == b"audio-51"


def test_search_without_provider_key_returns_warning(tmp_path: Path) -> None:
    settings = Settings(
        freesound_api_key=None,
        database_path=tmp_path / "missing-key.db",
        frontend_dir=Path("frontend"),
        preview_cache_dir=tmp_path / "previews",
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.post(
        "/api/search",
        json={"prompt": "boom", "source_filter": "freesound"},
    )

    assert response.status_code == 200
    assert response.json()["results"] == []
    assert "Freesound API 키" in response.json()["source_warnings"][0]


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
    assert results[0].source_provider == "freesound"
    assert results[0].source_id == "99"


def test_jamendo_client_normalizes_tracks_and_download_policy() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tracks/"
        assert request.url.params["client_id"] == "jamendo-id"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "123",
                        "name": "Loop Song",
                        "artist_name": "Composer",
                        "artist_id": "77",
                        "artist_idstr": "composer",
                        "duration": 64,
                        "audio": "https://prod-1.storage.jamendo.com/previews/123.mp3",
                        "audiodownload": "https://prod-1.storage.jamendo.com/download/123.mp3",
                        "audiodownload_allowed": True,
                        "shareurl": "https://www.jamendo.com/track/123/loop-song",
                        "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                        "musicinfo": {"tags": {"genres": ["cinematic", "game"]}},
                    }
                ]
            },
        )

    client = JamendoClient(
        client_id="jamendo-id",
        base_url="https://jamendo.test",
        transport=httpx.MockTransport(handler),
    )

    results = asyncio.run(
        client.search(
            query="loop",
            license_filter="commercial",
            min_duration=1,
            max_duration=120,
            page_size=5,
        )
    )

    assert results[0].source_provider == "jamendo"
    assert results[0].source_id == "123"
    assert results[0].license == "CC BY"
    assert results[0].download_allowed is True
    assert results[0].download_url is not None


def test_jamendo_download_disabled_when_api_denies_download() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "124",
                        "name": "Preview Only",
                        "artist_name": "Composer",
                        "duration": 30,
                        "audio": "https://prod-1.storage.jamendo.com/previews/124.mp3",
                        "audiodownload_allowed": False,
                        "license_ccurl": "https://creativecommons.org/licenses/by/4.0/",
                    }
                ]
            },
        )

    client = JamendoClient(
        client_id="jamendo-id",
        base_url="https://jamendo.test",
        transport=httpx.MockTransport(handler),
    )

    result = asyncio.run(client.search("loop", "commercial", 1, 120, 5))[0]

    assert result.preview_url is not None
    assert result.download_allowed is False
    assert result.download_url is None


def test_openverse_client_normalizes_audio_and_extracts_freesound_identity() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/audio/"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "openverse-id",
                        "title": "Open Boom",
                        "creator": "Creator",
                        "source": "freesound",
                        "foreign_identifier": "99",
                        "foreign_landing_url": "https://freesound.org/s/99/",
                        "url": "https://cdn.freesound.org/previews/99.mp3",
                        "duration": 7000,
                        "license": "by",
                        "license_version": "4.0",
                        "license_url": "https://creativecommons.org/licenses/by/4.0/",
                        "tags": [{"name": "boom"}],
                    }
                ]
            },
        )

    client = OpenverseClient(
        base_url="https://openverse.test",
        transport=httpx.MockTransport(handler),
    )

    results = asyncio.run(client.search("boom", "commercial", 0.1, 10, 5))

    assert results[0].source_provider == "freesound"
    assert results[0].source_id == "99"
    assert results[0].id == 99
    assert results[0].preview_url == "https://cdn.freesound.org/previews/99.mp3"


def test_openverse_client_uses_client_credentials_when_configured() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/auth_tokens/token/":
            return httpx.Response(200, json={"access_token": "openverse-token"})
        assert request.headers["Authorization"] == "Bearer openverse-token"
        return httpx.Response(200, json={"results": []})

    client = OpenverseClient(
        client_id="client-id",
        client_secret="client-secret",
        base_url="https://openverse.test",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(client.search("boom", "any", 0, 10, 5)) == []


def test_dedupe_prefers_direct_provider_over_openverse_duplicate() -> None:
    direct = SoundSearchResult(
        id=99,
        name="Direct",
        source_provider="freesound",
        source_id="99",
        preview_url="https://cdn.freesound.org/previews/99.mp3",
    )
    openverse_duplicate = SoundSearchResult(
        id=99,
        name="Openverse Copy",
        source_provider="freesound",
        source_id="99",
    )

    assert _dedupe_results([direct, openverse_duplicate]) == [direct]


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


def test_feedback_good_and_bad_are_mutually_exclusive(tmp_path: Path) -> None:
    database_path = tmp_path / "exclusive-feedback.db"
    base = {
        "id": 1,
        "prompt": "ui click",
        "name": "UI Click",
        "tags": ["ui", "click"],
    }

    save_feedback(database_path, FeedbackRequest(**base, feedback_type="good"))
    save_feedback(database_path, FeedbackRequest(**base, feedback_type="bad"))

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            "SELECT feedback_type FROM sound_feedback WHERE freesound_id = ?",
            (1,),
        ).fetchall()

    assert [row[0] for row in rows] == ["bad"]


def test_feedback_feature_tags_can_coexist(tmp_path: Path) -> None:
    database_path = tmp_path / "coexisting-feedback.db"
    base = {
        "id": 1,
        "prompt": "sharp heavy impact",
        "name": "Sharp Heavy Impact",
        "tags": ["sharp", "heavy", "impact"],
    }

    save_feedback(database_path, FeedbackRequest(**base, feedback_type="heavy_good"))
    save_feedback(database_path, FeedbackRequest(**base, feedback_type="sharp_good"))
    save_feedback(database_path, FeedbackRequest(**base, feedback_type="asset_ready"))

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT feedback_type
            FROM sound_feedback
            WHERE freesound_id = ?
            ORDER BY feedback_type
            """,
            (1,),
        ).fetchall()

    assert [row[0] for row in rows] == ["asset_ready", "heavy_good", "sharp_good"]


def test_feedback_can_be_deactivated(tmp_path: Path) -> None:
    database_path = tmp_path / "deactivated-feedback.db"
    request = FeedbackRequest(
        id=1,
        prompt="clean click",
        feedback_type="clean_good",
        name="Clean Click",
        tags=["clean", "click"],
    )

    save_feedback(database_path, request)
    response = save_feedback(
        database_path,
        FeedbackRequest(
            id=request.id,
            prompt=request.prompt,
            feedback_type=request.feedback_type,
            active=False,
            name=request.name,
            tags=request.tags,
        ),
    )

    with sqlite3.connect(database_path) as connection:
        count = connection.execute("SELECT COUNT(*) FROM sound_feedback").fetchone()[0]

    assert response.active is False
    assert count == 0


def test_negative_feedback_reason_types_are_stored(tmp_path: Path) -> None:
    database_path = tmp_path / "negative-reasons.db"
    base = {
        "id": 1,
        "prompt": "impact",
        "name": "Loud Impact",
        "tags": ["impact"],
    }

    save_feedback(database_path, FeedbackRequest(**base, feedback_type="too_loud"))
    save_feedback(database_path, FeedbackRequest(**base, feedback_type="wrong_mood"))

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT feedback_type
            FROM sound_feedback
            WHERE freesound_id = ?
            ORDER BY feedback_type
            """,
            (1,),
        ).fetchall()

    assert [row[0] for row in rows] == ["too_loud", "wrong_mood"]


def test_related_negative_feedback_is_capped(tmp_path: Path) -> None:
    database_path = tmp_path / "negative-cap.db"
    for index in range(12):
        save_feedback(
            database_path,
            FeedbackRequest(
                id=index + 1,
                prompt="boom",
                feedback_type="noise_bad",
                name=f"Noisy Boom {index}",
                tags=["boom", "noise"],
            ),
        )

    result = SoundSearchResult(id=99, name="Clean Boom", tags=["boom"])

    assert feedback_adjustment(database_path, result) == -10


def test_feedback_uses_cached_analysis_for_future_searches(tmp_path: Path) -> None:
    database_path = tmp_path / "analysis-feedback.db"
    save_analysis(
        database_path,
        SoundAnalysis(
            id=1,
            preview_url="https://cdn.freesound.org/previews/1.mp3",
            duration=1.2,
            waveform=[0.0, 0.8, 0.7, 0.04, 0.02],
            leading_silence_seconds=0.03,
            low_ratio=0.7,
            high_ratio=0.1,
            heaviness_score=88,
            sharpness_score=35,
            emptiness_score=8,
        ),
    )
    save_feedback(
        database_path,
        FeedbackRequest(
            id=1,
            prompt="heavy impact",
            feedback_type="heavy_good",
            name="Heavy Impact",
            tags=["impact"],
        ),
    )
    candidate_analysis = SoundAnalysis(
        id=2,
        preview_url="https://cdn.freesound.org/previews/2.mp3",
        duration=1.1,
        waveform=[0.0, 0.76, 0.68, 0.05, 0.02],
        leading_silence_seconds=0.04,
        low_ratio=0.68,
        high_ratio=0.12,
        heaviness_score=84,
        sharpness_score=38,
        emptiness_score=10,
    )
    result = SoundSearchResult(id=2, name="New Impact", tags=["impact"])

    assert feedback_adjustment(database_path, result, analysis=candidate_analysis) > 0


def test_existing_analysis_table_is_migrated_before_feedback_lookup(tmp_path: Path) -> None:
    database_path = tmp_path / "old-analysis-schema.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE sound_analyses (
                freesound_id INTEGER PRIMARY KEY,
                preview_url TEXT NOT NULL,
                waveform TEXT NOT NULL DEFAULT '[]',
                rms REAL NOT NULL DEFAULT 0,
                peak REAL NOT NULL DEFAULT 0,
                leading_silence_seconds REAL NOT NULL DEFAULT 0,
                low_ratio REAL NOT NULL DEFAULT 0,
                mid_ratio REAL NOT NULL DEFAULT 0,
                high_ratio REAL NOT NULL DEFAULT 0,
                spectral_centroid_hz REAL NOT NULL DEFAULT 0,
                heaviness_score INTEGER NOT NULL DEFAULT 0,
                sharpness_score INTEGER NOT NULL DEFAULT 0,
                emptiness_score INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

    adjustment = feedback_adjustment(database_path, SoundSearchResult(id=1, name="Test"))

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sound_analyses)").fetchall()
        }
    assert adjustment == 0
    assert "duration" in columns


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
