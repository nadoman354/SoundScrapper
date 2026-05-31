from __future__ import annotations

from statistics import fmean

from backend.app.prompt_parser import ParsedPrompt
from backend.app.schemas import SoundAnalysis, SoundSearchResult


NOISE_AMBIENCE_TERMS = (
    "ambience",
    "ambient noise",
    "atmosphere",
    "background noise",
    "crowd",
    "field recording",
    "field-recording",
    "hiss",
    "hum",
    "noise",
    "noisy",
    "room tone",
    "street",
    "traffic",
    "wind",
)
SFX_TERMS = (
    "button",
    "click",
    "explosion",
    "foley",
    "hit",
    "impact",
    "jump",
    "laser",
    "one shot",
    "one-shot",
    "pickup",
    "sfx",
    "slash",
    "spell",
    "ui",
    "whoosh",
)
BGM_TERMS = (
    "bgm",
    "game music",
    "loop",
    "loopable",
    "music",
    "ost",
    "seamless",
    "theme",
)
CLEAN_TERMS = (
    "clean",
    "designed",
    "dry",
    "isolated",
    "processed",
    "studio",
)


def _with_score(
    result: SoundSearchResult,
    score: int,
    reasons: list[str] | None = None,
) -> SoundSearchResult:
    clamped = max(0, min(100, score))
    update = {"score": clamped}
    if reasons is not None:
        update["score_reasons"] = reasons
    if hasattr(result, "model_copy"):
        return result.model_copy(update=update)
    return result.copy(update=update)


def score_sound(
    result: SoundSearchResult,
    parsed_prompt: ParsedPrompt,
    min_duration: float,
    max_duration: float,
    game_ready: bool = False,
    analysis: SoundAnalysis | None = None,
) -> SoundSearchResult:
    score = 45
    reasons = ["기본 점수 +45"]
    license_text = result.license.lower()

    if "creative commons 0" in license_text or "publicdomain/zero" in license_text:
        score += 25
        reasons.append("CC0 라이선스 +25")
    elif "attribution" in license_text and "noncommercial" not in license_text:
        score += 15
        reasons.append("상업 사용 가능 라이선스 +15")
    elif "noncommercial" in license_text:
        score -= 30
        reasons.append("비상업 라이선스 -30")

    if min_duration <= result.duration <= max_duration:
        score += 10
        reasons.append("길이 조건 일치 +10")
    elif result.duration > max_duration:
        penalty = min(20, int(result.duration - max_duration) * 4)
        score -= penalty
        if penalty:
            reasons.append(f"길이 초과 -{penalty}")

    searchable_text = _searchable_text(result)
    matched_terms = [term for term in parsed_prompt.include_terms if term in searchable_text]
    match_bonus = min(20, len(set(matched_terms)) * 4)
    score += match_bonus
    if match_bonus:
        sample = ", ".join(sorted(set(matched_terms))[:4])
        reasons.append(f"검색어 일치 +{match_bonus} ({sample})")

    if result.preview_url:
        score += 5
        reasons.append("미리듣기 있음 +5")

    if game_ready:
        game_adjustment, game_reasons = _game_ready_adjustment(
            result=result,
            text=searchable_text,
            analysis=analysis,
        )
        score += game_adjustment
        reasons.extend(game_reasons)

    return _with_score(result, score, reasons)


def sort_ranked(results: list[SoundSearchResult]) -> list[SoundSearchResult]:
    return sorted(results, key=lambda item: (item.score, -item.duration), reverse=True)


def _searchable_text(result: SoundSearchResult) -> str:
    return " ".join(
        [
            result.name,
            result.description or "",
            " ".join(result.tags),
        ]
    ).lower()


def _game_ready_adjustment(
    result: SoundSearchResult,
    text: str,
    analysis: SoundAnalysis | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    has_bgm_signal = _contains_any(text, BGM_TERMS)

    if result.duration <= 3:
        score += 12
        reasons.append("게임용: 짧은 SFX 후보 +12")
    elif result.duration <= 8:
        score += 6
        reasons.append("게임용: 짧게 편집 가능한 길이 +6")
    elif has_bgm_signal:
        score += 8
        reasons.append("게임용: BGM/루프 후보 +8")
    else:
        penalty = min(14, max(4, int((result.duration - 8) / 4) * 3))
        score -= penalty
        reasons.append(f"게임용: 긴 단일 파일 주의 -{penalty}")

    if _contains_any(text, SFX_TERMS):
        score += 10
        reasons.append("게임용: SFX 태그/제목 +10")

    if _contains_any(text, CLEAN_TERMS):
        score += 6
        reasons.append("게임용: 깨끗한 소스 단서 +6")

    if _contains_any(text, NOISE_AMBIENCE_TERMS):
        penalty = 8 if has_bgm_signal else 16
        score -= penalty
        reasons.append(f"게임용: 환경음/잡음 단서 -{penalty}")

    if analysis:
        analysis_score, analysis_reasons = _analysis_game_adjustment(analysis)
        score += analysis_score
        reasons.extend(analysis_reasons)

    return max(-35, min(35, score)), reasons


def _analysis_game_adjustment(analysis: SoundAnalysis) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if analysis.leading_silence_seconds <= 0.2:
        score += 6
        reasons.append("게임용: 앞 무음 적음 +6")
    elif analysis.leading_silence_seconds >= 0.6:
        score -= 10
        reasons.append("게임용: 앞 무음 김 -10")

    if analysis.emptiness_score <= 18:
        score += 6
        reasons.append("게임용: 빈 구간 적음 +6")
    elif analysis.emptiness_score >= 45:
        score -= 10
        reasons.append("게임용: 빈 구간 많음 -10")

    if analysis.sharpness_score >= 82:
        score -= 5
        reasons.append("게임용: 과한 날카로움 주의 -5")

    event_count = _estimate_waveform_events(analysis.waveform)
    if event_count >= 2:
        score += 8
        reasons.append("게임용: 파형 분리 쉬움 +8")
    elif event_count == 1 and analysis.duration <= 4:
        score += 5
        reasons.append("게임용: 원샷 컷오프 쉬움 +5")

    return score, reasons


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _estimate_waveform_events(waveform: list[float]) -> int:
    values = [max(0.0, min(1.0, value)) for value in waveform if value >= 0]
    if not values:
        return 0

    average = fmean(values)
    peak = max(values)
    if peak < 0.12:
        return 0

    threshold = max(0.18, average + (peak - average) * 0.35)
    quiet_threshold = max(0.08, threshold * 0.38)
    events = 0
    in_event = False
    quiet_run = 0

    for value in values:
        if value >= threshold:
            if not in_event:
                events += 1
                in_event = True
            quiet_run = 0
        elif in_event and value <= quiet_threshold:
            quiet_run += 1
            if quiet_run >= 2:
                in_event = False
                quiet_run = 0
        elif in_event:
            quiet_run = 0

    return events
