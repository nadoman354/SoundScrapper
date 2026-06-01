from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LicenseFilter = Literal["commercial", "cc0", "any"]
SourceFilter = Literal["all", "freesound", "jamendo", "openverse"]
SearchMode = Literal[
    "clean_source",
    "short_sfx",
    "easy_cut",
    "loop_bgm",
    "rights_safe",
]
FeedbackType = Literal[
    "good",
    "bad",
    "game_like",
    "asset_ready",
    "heavy_good",
    "sharp_good",
    "clean_good",
    "easy_cut",
    "loop_good",
    "noise_bad",
    "leading_silence_bad",
    "too_sharp",
    "too_loud",
    "too_long",
    "low_quality",
    "wrong_mood",
    "license_risky",
]


class HealthResponse(BaseModel):
    status: str


class ProviderStatus(BaseModel):
    provider: str
    configured: bool
    enabled: bool
    message: str = ""
    base_url: str | None = None


class ProviderStatusResponse(BaseModel):
    providers: list[ProviderStatus]


class SearchRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    license: LicenseFilter = "commercial"
    min_duration: float = Field(0.1, ge=0)
    max_duration: float = Field(3.0, gt=0)
    page_size: int = Field(20, ge=1, le=50)
    game_ready: bool = False
    search_modes: list[SearchMode] = Field(default_factory=list)
    source_filter: SourceFilter = "all"


class SoundSearchResult(BaseModel):
    id: int
    name: str
    username: str = ""
    license: str = ""
    duration: float = 0
    tags: list[str] = Field(default_factory=list)
    preview_url: str | None = None
    url: str | None = None
    description: str | None = None
    score: int = 0
    personal_score_adjustment: int = 0
    score_reasons: list[str] = Field(default_factory=list)
    source_provider: str = "freesound"
    source_id: str = ""
    source_url: str | None = None
    license_url: str | None = None
    creator_url: str | None = None
    attribution_text: str | None = None
    download_url: str | None = None
    download_allowed: bool = True


class SoundAnalysis(BaseModel):
    id: int
    preview_url: str
    waveform: list[float] = Field(default_factory=list)
    duration: float = 0
    rms: float = 0
    peak: float = 0
    leading_silence_seconds: float = 0
    low_ratio: float = 0
    mid_ratio: float = 0
    high_ratio: float = 0
    spectral_centroid_hz: float = 0
    heaviness_score: int = 0
    sharpness_score: int = 0
    emptiness_score: int = 0
    updated_at: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SoundSearchResult]
    source_warnings: list[str] = Field(default_factory=list)


class SavedSound(BaseModel):
    saved_id: int
    saved_at: str
    id: int
    name: str
    username: str = ""
    license: str = ""
    duration: float = 0
    tags: list[str] = Field(default_factory=list)
    preview_url: str | None = None
    url: str | None = None
    description: str | None = None
    score: int = 0
    feedback_types: list[str] = Field(default_factory=list)
    source_provider: str = "freesound"
    source_id: str = ""
    source_url: str | None = None
    license_url: str | None = None
    creator_url: str | None = None
    attribution_text: str | None = None
    download_url: str | None = None
    download_allowed: bool = True


class FeedbackRequest(BaseModel):
    id: int
    prompt: str = ""
    feedback_type: FeedbackType
    active: bool = True
    name: str = ""
    tags: list[str] = Field(default_factory=list)
    source_provider: str = "freesound"
    source_id: str = ""


class FeedbackResponse(BaseModel):
    id: int
    freesound_id: int
    feedback_type: FeedbackType
    active: bool = True
    created_at: str


class PreviewCacheResponse(BaseModel):
    id: int
    audio_url: str
