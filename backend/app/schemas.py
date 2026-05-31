from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


LicenseFilter = Literal["commercial", "cc0", "any"]
FeedbackType = Literal["good", "bad", "heavy_good", "too_sharp", "magic_feel"]


class HealthResponse(BaseModel):
    status: str


class SearchRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    license: LicenseFilter = "commercial"
    min_duration: float = Field(0.1, ge=0)
    max_duration: float = Field(3.0, gt=0)
    page_size: int = Field(20, ge=1, le=50)
    game_ready: bool = False


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


class FeedbackRequest(BaseModel):
    id: int
    prompt: str = ""
    feedback_type: FeedbackType
    name: str = ""
    tags: list[str] = Field(default_factory=list)


class FeedbackResponse(BaseModel):
    id: int
    freesound_id: int
    feedback_type: FeedbackType
    created_at: str


class PreviewCacheResponse(BaseModel):
    id: int
    audio_url: str
