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
    search_modes: list[str] | None = None,
    analysis: SoundAnalysis | None = None,
) -> SoundSearchResult:
    score = 45
    reasons = ["기본 점수 +45"]
    license_text = result.license.lower()

    if "creative commons 0" in license_text or "publicdomain/zero" in license_text or "cc0" in license_text:
        score += 25
        reasons.append("CC0 라이선스 +25")
    elif "nc" in license_text or "noncommercial" in license_text:
        score -= 30
        reasons.append("비상업 라이선스 -30")
    elif "nd" in license_text:
        score -= 18
        reasons.append("변경금지 라이선스 -18")
    elif "attribution" in license_text or "cc by" in license_text:
        score += 15
        reasons.append("상업 사용 가능 라이선스 +15")

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

    source_score, source_reasons = _source_adjustment(result, set(search_modes or []))
    score += source_score
    reasons.extend(source_reasons)

    if game_ready:
        game_adjustment, game_reasons = _game_ready_adjustment(
            result=result,
            text=searchable_text,
            analysis=analysis,
        )
        score += game_adjustment
        reasons.extend(game_reasons)

    mode_adjustment, mode_reasons = _search_mode_adjustment(
        result=result,
        text=searchable_text,
        modes=set(search_modes or []),
        analysis=analysis,
        license_text=license_text,
    )
    score += mode_adjustment
    reasons.extend(mode_reasons)

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


def _search_mode_adjustment(
    result: SoundSearchResult,
    text: str,
    modes: set[str],
    analysis: SoundAnalysis | None,
    license_text: str,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if "clean_source" in modes:
        clean_score, clean_reasons = _clean_source_adjustment(text, analysis)
        score += clean_score
        reasons.extend(clean_reasons)

    if "short_sfx" in modes:
        short_score, short_reasons = _short_sfx_adjustment(result, text)
        score += short_score
        reasons.extend(short_reasons)

    if "easy_cut" in modes:
        cut_score, cut_reasons = _easy_cut_adjustment(result, analysis)
        score += cut_score
        reasons.extend(cut_reasons)

    if "loop_bgm" in modes:
        loop_score, loop_reasons = _loop_bgm_adjustment(result, text, analysis)
        score += loop_score
        reasons.extend(loop_reasons)

    if "rights_safe" in modes:
        rights_score, rights_reasons = _rights_safe_adjustment(license_text)
        score += rights_score
        reasons.extend(rights_reasons)

    return max(-45, min(45, score)), reasons


def _clean_source_adjustment(
    text: str,
    analysis: SoundAnalysis | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if _contains_any(text, CLEAN_TERMS):
        score += 10
        reasons.append("조건: 깨끗한 소스 단서 +10")
    if _contains_any(text, NOISE_AMBIENCE_TERMS):
        score -= 18
        reasons.append("조건: 환경음/잡음 단서 -18")
    if analysis:
        if analysis.emptiness_score <= 18 and analysis.leading_silence_seconds <= 0.25:
            score += 6
            reasons.append("조건: 분석상 빈 구간/앞 무음 적음 +6")
        elif analysis.emptiness_score >= 45:
            score -= 8
            reasons.append("조건: 분석상 빈 구간 많음 -8")

    return score, reasons


def _short_sfx_adjustment(result: SoundSearchResult, text: str) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if result.duration <= 3:
        score += 14
        reasons.append("조건: 짧은 원샷 길이 +14")
    elif result.duration > 5:
        score -= 14
        reasons.append("조건: 원샷 SFX로는 긴 편 -14")
    if _contains_any(text, SFX_TERMS):
        score += 8
        reasons.append("조건: SFX 단서 +8")
    if _contains_any(text, BGM_TERMS):
        score -= 10
        reasons.append("조건: BGM/루프 단서 -10")

    return score, reasons


def _easy_cut_adjustment(
    result: SoundSearchResult,
    analysis: SoundAnalysis | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if analysis is None:
        if result.preview_url:
            reasons.append("조건: 파형 분석 후 컷오프 판단 가능")
        return score, reasons

    event_count = _estimate_waveform_events(analysis.waveform)
    if event_count >= 2:
        score += 12
        reasons.append("조건: 파형 이벤트 분리 +12")
    elif event_count == 1 and analysis.duration <= 4:
        score += 7
        reasons.append("조건: 원샷 컷오프 쉬움 +7")
    if analysis.leading_silence_seconds <= 0.2:
        score += 4
        reasons.append("조건: 앞 무음 적음 +4")
    elif analysis.leading_silence_seconds >= 0.6:
        score -= 7
        reasons.append("조건: 앞 무음 김 -7")

    return score, reasons


def _loop_bgm_adjustment(
    result: SoundSearchResult,
    text: str,
    analysis: SoundAnalysis | None,
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []

    if _contains_any(text, BGM_TERMS):
        score += 14
        reasons.append("조건: BGM/루프 단서 +14")
    if result.duration >= 4:
        score += 8
        reasons.append("조건: 루프/BGM에 맞는 길이 +8")
    elif result.duration <= 1.5:
        score -= 12
        reasons.append("조건: 루프/BGM으로는 짧음 -12")
    if _contains_any(text, SFX_TERMS) and result.duration <= 3:
        score -= 8
        reasons.append("조건: 짧은 SFX 단서 -8")
    if analysis and analysis.emptiness_score <= 20 and analysis.leading_silence_seconds <= 0.3:
        score += 4
        reasons.append("조건: 분석상 루프 가공 여지 +4")

    return score, reasons


def _source_adjustment(
    result: SoundSearchResult,
    modes: set[str],
) -> tuple[int, list[str]]:
    provider = result.source_provider.lower()
    score = 0
    reasons = []

    if provider == "freesound" and "short_sfx" in modes:
        score += 6
        reasons.append("출처: Freesound SFX 우선 +6")
    if provider == "jamendo":
        if "loop_bgm" in modes:
            score += 10
            reasons.append("출처: Jamendo BGM 후보 +10")
        if "short_sfx" in modes:
            score -= 10
            reasons.append("출처: Jamendo는 짧은 SFX에 약함 -10")
    if provider not in {"freesound", "jamendo"} and "loop_bgm" in modes:
        score += 3
        reasons.append("출처: Openverse 음악 보강 +3")

    return score, reasons


def _rights_safe_adjustment(license_text: str) -> tuple[int, list[str]]:
    normalized = license_text.lower()
    if "creative commons 0" in normalized or "publicdomain/zero" in normalized or "cc0" in normalized:
        return 12, ["조건: 저작권 안전 CC0 +12"]
    if "nc" in normalized or "noncommercial" in normalized:
        return -25, ["조건: 비상업 라이선스 제외 권장 -25"]
    if "nd" in normalized:
        return -18, ["조건: 변경금지 라이선스 편집 주의 -18"]
    if "sa" in normalized:
        return -8, ["조건: 동일조건변경허락 라이선스 주의 -8"]
    if "attribution" in normalized or "cc by" in normalized:
        return 5, ["조건: 저작자 표시 라이선스 +5"]
    return -4, ["조건: 라이선스 확인 필요 -4"]


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
