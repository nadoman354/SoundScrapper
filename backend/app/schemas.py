from __future__ import annotations

from typing import Any, Literal

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


class FreesoundAuthStatus(BaseModel):
    configured: bool
    logged_in: bool
    username: str | None = None
    expires_at: int | None = None
    message: str = ""


class FreesoundOAuthStartResponse(BaseModel):
    authorize_url: str


class FreesoundOAuthExchangeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=500)


class SearchRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    license: LicenseFilter = "commercial"
    min_duration: float = Field(0.1, ge=0)
    max_duration: float = Field(3.0, gt=0)
    page_size: int = Field(20, ge=1, le=50)
    game_ready: bool = False
    search_modes: list[SearchMode] = Field(default_factory=list)
    source_filter: SourceFilter = "all"
    use_prompt_interpretation: bool = True
    use_behavior_personalization: bool = True


class SearchSuggestion(BaseModel):
    label: str
    prompt: str
    reason: str = ""


class SearchSuggestionsResponse(BaseModel):
    suggestions: list[SearchSuggestion] = Field(default_factory=list)


class SearchInterpretationResponse(BaseModel):
    query: str
    interpreted_concepts: list[str] = Field(default_factory=list)
    negative_concepts: list[str] = Field(default_factory=list)
    fallback_queries: list[str] = Field(default_factory=list)
    suggestions: list[SearchSuggestion] = Field(default_factory=list)
    interpretation_enabled: bool = True


class AIStatusResponse(BaseModel):
    configured: bool
    reachable: bool
    message: str = ""
    base_url: str | None = None
    model: str | None = None


class AISearchAssistRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=500)
    license: LicenseFilter = "commercial"
    min_duration: float = Field(0.1, ge=0)
    max_duration: float = Field(3.0, gt=0)
    source_filter: SourceFilter = "all"
    use_behavior_personalization: bool = True
    behavior_profile: dict[str, Any] = Field(default_factory=dict)


class AISearchAssistResponse(BaseModel):
    enabled: bool = False
    primary_query: str = ""
    alternative_queries: list[SearchSuggestion] = Field(default_factory=list)
    translated_intent: str = ""
    intent_label: str = ""
    sound_type: str = "unknown"
    preferred_duration: str = ""
    avoid_concepts: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    deprioritize_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model: str | None = None


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
    download_count: int | None = None


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
    interpreted_concepts: list[str] = Field(default_factory=list)
    negative_concepts: list[str] = Field(default_factory=list)
    suggested_queries: list[SearchSuggestion] = Field(default_factory=list)
    fallback_queries_used: list[str] = Field(default_factory=list)
    search_failed: bool = False


class BehaviorEvent(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=60)
    search_session_id: str = Field("", max_length=120)
    source_provider: str = Field("", max_length=80)
    source_id: str = Field("", max_length=120)
    prompt: str = Field("", max_length=500)
    query: str = Field("", max_length=500)
    result_rank: int | None = Field(None, ge=0)
    duration: float | None = Field(None, ge=0)
    listen_seconds: float | None = Field(None, ge=0)
    progress_ratio: float | None = Field(None, ge=0, le=1)
    filters: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class BehaviorEventsRequest(BaseModel):
    events: list[BehaviorEvent] = Field(..., min_length=1, max_length=100)


class BehaviorEventsResponse(BaseModel):
    saved_count: int = 0


class BehaviorProfileResponse(BaseModel):
    total_events: int = 0
    positive_terms: list[str] = Field(default_factory=list)
    negative_terms: list[str] = Field(default_factory=list)
    preferred_sources: list[str] = Field(default_factory=list)
    avoided_sources: list[str] = Field(default_factory=list)
    preferred_duration_seconds: float | None = None
    summary_lines: list[str] = Field(default_factory=list)


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
    download_count: int | None = None
    note: str = ""
    fit_rating: int | None = Field(None, ge=1, le=5)
    folder: str = ""
    labels: list[str] = Field(default_factory=list)
    download_filename: str = ""


class SavedSoundUpdate(BaseModel):
    note: str | None = Field(None, max_length=2000)
    fit_rating: int | None = Field(None, ge=1, le=5)
    folder: str | None = Field(None, max_length=80)
    labels: list[str] | None = Field(None, max_length=20)
    download_filename: str | None = Field(None, max_length=120)


class SavedFolder(BaseModel):
    folder_id: int
    name: str
    sort_order: int = 0
    sound_count: int = 0
    created_at: str | None = None


class SavedFolderCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


class SavedFolderUpdate(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)


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
