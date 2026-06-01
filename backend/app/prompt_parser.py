from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ConceptRule:
    triggers: tuple[str, ...]
    terms: tuple[str, ...]
    concepts: tuple[str, ...]
    intents: tuple[str, ...] = ()


@dataclass(frozen=True)
class NegativeRule:
    triggers: tuple[str, ...]
    negative_terms: tuple[str, ...]
    concepts: tuple[str, ...]
    query_terms: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()


CONCEPT_RULES: tuple[ConceptRule, ...] = (
    ConceptRule(
        ("explosion", "boom", "impact", "blast", "폭발", "폭발음", "터지는", "터짐"),
        ("explosion", "boom", "impact", "blast"),
        ("폭발",),
        ("sfx",),
    ),
    ConceptRule(
        ("hit", "punch", "타격", "때리는", "맞는", "충격", "충돌"),
        ("hit", "impact", "punch", "thud"),
        ("타격",),
        ("sfx",),
    ),
    ConceptRule(
        ("sword", "slash", "blade", "검", "칼", "베기", "베는", "참격"),
        ("sword", "slash", "blade", "whoosh"),
        ("검격",),
        ("sfx",),
    ),
    ConceptRule(
        ("whoosh", "swing", "swoosh", "휘두르", "휙", "스윙"),
        ("whoosh", "swing", "swoosh"),
        ("휘두름",),
        ("sfx",),
    ),
    ConceptRule(
        ("shoot", "gun", "총", "총소리", "발사", "사격"),
        ("gun", "shot", "shoot", "firearm"),
        ("총격",),
        ("sfx",),
    ),
    ConceptRule(
        ("laser", "레이저", "빔"),
        ("laser", "beam", "sci-fi"),
        ("레이저",),
        ("sfx",),
    ),
    ConceptRule(
        ("magic", "spell", "magical", "마법", "주문", "스킬"),
        ("magic", "spell", "fantasy"),
        ("마법",),
        ("sfx",),
    ),
    ConceptRule(
        ("footstep", "footsteps", "발소리", "걸음"),
        ("footstep", "footsteps", "walk"),
        ("발소리",),
        ("sfx",),
    ),
    ConceptRule(
        ("button", "click", "ui", "버튼", "클릭", "선택음", "메뉴음"),
        ("button", "click", "ui"),
        ("UI 클릭",),
        ("sfx",),
    ),
    ConceptRule(
        ("door", "문", "문소리", "열리는", "닫히는"),
        ("door", "open", "close", "creak"),
        ("문",),
        ("sfx",),
    ),
    ConceptRule(
        ("wind", "바람"),
        ("wind",),
        ("바람",),
    ),
    ConceptRule(
        ("fire", "flame", "불", "화염"),
        ("fire", "flame"),
        ("불/화염",),
    ),
    ConceptRule(
        ("water", "물", "물소리", "파도"),
        ("water", "splash", "wave"),
        ("물",),
    ),
    ConceptRule(
        ("kick drum", "킥 드럼", "킥드럼"),
        ("kick", "drum"),
        ("킥 드럼",),
        ("sfx",),
    ),
    ConceptRule(
        ("snare", "snare drum", "스네어"),
        ("snare", "drum"),
        ("스네어",),
        ("sfx",),
    ),
    ConceptRule(
        ("drum", "percussion", "드럼", "북소리", "타악기"),
        ("drum", "percussion"),
        ("드럼",),
        ("sfx",),
    ),
    ConceptRule(
        ("circuit", "회로"),
        ("circuit", "electric"),
        ("전기/회로",),
        ("sfx",),
    ),
    ConceptRule(
        ("electric", "electricity", "전기", "감전"),
        ("electric", "spark", "zap"),
        ("전기",),
        ("sfx",),
    ),
    ConceptRule(
        ("buzz", "static", "지지직", "노이즈"),
        ("electric", "buzz", "static"),
        ("지지직",),
        ("sfx",),
    ),
    ConceptRule(
        ("heavy", "bass", "low", "묵직", "둔탁", "저음", "박력"),
        ("heavy", "low", "bass", "boom"),
        ("묵직함",),
        ("heavy",),
    ),
    ConceptRule(
        ("sharp", "metallic", "날카", "쨍한", "금속성"),
        ("sharp", "metallic"),
        ("날카로움",),
        ("sharp",),
    ),
    ConceptRule(
        ("clean", "dry", "isolated", "깨끗", "선명", "깔끔", "소스"),
        ("clean", "dry", "isolated", "studio"),
        ("깨끗한 소스",),
        ("clean",),
    ),
    ConceptRule(
        ("short", "one-shot", "oneshot", "짧", "원샷", "짧은"),
        ("short", "one-shot", "sfx"),
        ("짧은 SFX",),
        ("sfx", "short"),
    ),
    ConceptRule(
        ("calm", "soft", "잔잔", "차분", "평온", "조용한"),
        ("calm", "soft", "ambient"),
        ("잔잔함",),
        ("bgm",),
    ),
    ConceptRule(
        ("dark", "shadow", "eerie", "암흑", "어둠", "다크", "음산"),
        ("dark", "deep", "eerie"),
        ("어두움",),
    ),
    ConceptRule(
        ("cute", "cartoon", "귀여", "아기자기"),
        ("cute", "happy", "cartoon"),
        ("귀여움",),
    ),
    ConceptRule(
        ("cyber", "retro", "8bit", "8-bit", "사이버", "레트로", "8비트", "픽셀"),
        ("retro", "8-bit", "chiptune", "sci-fi"),
        ("사이버/레트로",),
    ),
    ConceptRule(
        ("bgm", "music", "브금", "배경음악", "음악", "ost"),
        ("bgm", "music"),
        ("BGM",),
        ("bgm",),
    ),
    ConceptRule(
        ("loop", "loopable", "seamless", "루프", "반복"),
        ("loop", "loopable", "seamless"),
        ("루프",),
        ("bgm", "loop"),
    ),
    ConceptRule(
        ("battle", "combat", "전투", "액션"),
        ("battle", "combat", "action"),
        ("전투",),
        ("bgm",),
    ),
    ConceptRule(
        ("tension", "suspense", "긴장", "불안"),
        ("tension", "suspense", "dark"),
        ("긴장감",),
        ("bgm",),
    ),
    ConceptRule(
        ("menu", "메뉴", "로비"),
        ("menu", "ui", "music"),
        ("메뉴",),
        ("bgm",),
    ),
    ConceptRule(
        ("boss", "보스", "보스전"),
        ("boss", "battle"),
        ("보스전",),
        ("bgm",),
    ),
    ConceptRule(
        ("game", "게임", "효과음", "게임용", "sfx"),
        ("game", "sfx"),
        ("게임용",),
        ("sfx",),
    ),
)

NEGATIVE_RULES: tuple[NegativeRule, ...] = (
    NegativeRule(
        (
            "잡음 없이",
            "잡음 없음",
            "잡음없",
            "노이즈 없이",
            "노이즈 없음",
            "소음 없이",
            "소음 없음",
            "환경음 제외",
            "환경음 없이",
            "배경소음 없이",
            "no noise",
            "without noise",
            "noise free",
            "no ambience",
            "without ambience",
        ),
        (
            "noise",
            "noisy",
            "ambience",
            "ambient",
            "ambient noise",
            "field recording",
            "hiss",
            "hum",
            "room tone",
            "traffic",
            "crowd",
        ),
        ("잡음/환경음 제외",),
        ("clean", "dry", "isolated"),
        ("clean",),
    ),
    NegativeRule(
        (
            "보컬 없음",
            "보컬 없이",
            "목소리 없이",
            "목소리 없음",
            "음성 제외",
            "말소리 제외",
            "no vocal",
            "no vocals",
            "without vocal",
            "without vocals",
            "no voice",
        ),
        ("vocal", "vocals", "voice", "speech", "talking", "dialogue"),
        ("보컬/음성 제외",),
    ),
    NegativeRule(
        (
            "날카롭지 않은",
            "날카롭지 않",
            "너무 날카롭지",
            "쨍하지 않",
            "not sharp",
            "less sharp",
        ),
        ("sharp", "metallic", "shrill", "piercing"),
        ("날카로움 제외",),
    ),
    NegativeRule(
        (
            "너무 길지",
            "길지 않은",
            "길지 않",
            "짧게",
            "not long",
            "too long",
        ),
        ("long", "extended"),
        ("긴 사운드 제외",),
        ("short", "one-shot"),
        ("short", "sfx"),
    ),
)

NEGATIVE_SUPPRESSED_CONCEPTS = {
    "날카로움 제외": ("날카로움",),
}

ENGLISH_STOP_WORDS = {"less", "no", "not", "too", "without"}


@dataclass(frozen=True)
class ParsedPrompt:
    original: str
    query: str
    include_terms: tuple[str, ...]
    interpreted_concepts: tuple[str, ...] = ()
    negative_concepts: tuple[str, ...] = ()
    negative_terms: tuple[str, ...] = ()
    intent_flags: tuple[str, ...] = ()
    fallback_queries: tuple[str, ...] = ()
    suggestion_concepts: tuple[str, ...] = ()


@dataclass(frozen=True)
class PromptSuggestion:
    label: str
    prompt: str
    reason: str


CONCEPT_SUGGESTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "폭발": (
        ("explosion impact", "폭발음을 짧은 충격음 중심으로 좁힙니다."),
        ("cinematic boom", "더 묵직한 폭발 후보를 찾습니다."),
        ("blast hit", "게임 SFX에서 잘 쓰이는 짧은 폭발 표현입니다."),
    ),
    "타격": (
        ("impact hit", "타격과 충격 후보를 넓게 찾습니다."),
        ("punch thud", "둔탁한 타격 후보를 찾습니다."),
        ("body hit impact", "캐릭터 피격음 후보에 가깝게 좁힙니다."),
    ),
    "검격": (
        ("sword slash", "검 베기 후보를 가장 직접적으로 찾습니다."),
        ("blade whoosh", "검을 휘두르는 바람 소리 쪽으로 좁힙니다."),
        ("sword hit", "칼이 맞닿는 충돌음 후보를 찾습니다."),
    ),
    "휘두름": (
        ("fast whoosh", "빠른 휘두름 후보를 찾습니다."),
        ("weapon swing", "무기 스윙 계열로 좁힙니다."),
    ),
    "총격": (
        ("gun shot", "총격 후보를 직접적으로 찾습니다."),
        ("single gunshot", "짧은 단발 총소리 후보를 찾습니다."),
    ),
    "레이저": (
        ("laser shot", "레이저 발사 후보를 찾습니다."),
        ("sci-fi beam", "SF 빔 사운드 쪽으로 넓힙니다."),
    ),
    "마법": (
        ("magic spell", "주문/마법 후보를 직접적으로 찾습니다."),
        ("fantasy impact", "게임 스킬 충격음 후보를 찾습니다."),
        ("dark magic", "어두운 마법 느낌으로 좁힙니다."),
    ),
    "발소리": (
        ("footstep walk", "일반 발소리 후보를 찾습니다."),
        ("single footstep", "짧은 단일 발소리 후보를 찾습니다."),
    ),
    "UI 클릭": (
        ("ui click", "UI 클릭 사운드를 직접적으로 찾습니다."),
        ("button click", "버튼 클릭 후보를 찾습니다."),
        ("menu select", "메뉴 선택음 후보를 찾습니다."),
    ),
    "문": (
        ("door open", "문 열림 사운드를 찾습니다."),
        ("door close", "문 닫힘 사운드를 찾습니다."),
        ("door creak", "삐걱이는 문소리 후보를 찾습니다."),
    ),
    "드럼": (
        ("drum hit", "짧은 드럼 히트 후보를 찾습니다."),
        ("percussion loop", "타악기 루프 후보를 찾습니다."),
        ("drum fill", "드럼 필인 후보를 찾습니다."),
    ),
    "킥 드럼": (
        ("kick drum", "킥 드럼 후보를 직접 찾습니다."),
        ("bass drum hit", "저역이 있는 킥/베이스 드럼 후보를 찾습니다."),
    ),
    "스네어": (
        ("snare drum", "스네어 후보를 직접 찾습니다."),
        ("snare hit", "짧은 스네어 히트 후보를 찾습니다."),
    ),
    "전기/회로": (
        ("circuit electric", "회로나 전기 장치 느낌으로 찾습니다."),
        ("electric buzz", "전기가 지지직거리는 후보를 찾습니다."),
        ("spark zap", "스파크/감전 계열 후보를 찾습니다."),
    ),
    "전기": (
        ("electric spark", "전기 스파크 후보를 찾습니다."),
        ("zap shock", "감전/전격 느낌의 후보를 찾습니다."),
    ),
    "지지직": (
        ("electric buzz", "전기 노이즈 후보를 찾습니다."),
        ("static buzz", "지지직거리는 정적 노이즈 후보를 찾습니다."),
    ),
    "묵직함": (
        ("heavy impact", "묵직한 충격음 표현으로 다시 찾습니다."),
        ("low boom", "저역이 강조된 후보를 찾습니다."),
        ("bass hit", "저음 타격감이 있는 후보를 찾습니다."),
    ),
    "깨끗한 소스": (
        ("clean dry sfx", "배경음이 적은 단독 효과음을 찾습니다."),
        ("isolated sound effect", "분리된 소스 후보를 찾습니다."),
    ),
    "짧은 SFX": (
        ("short one-shot sfx", "짧은 원샷 효과음으로 좁힙니다."),
        ("game sfx short", "게임용 짧은 효과음 후보를 찾습니다."),
    ),
    "잔잔함": (
        ("calm loop", "잔잔하게 반복 가능한 후보를 찾습니다."),
        ("soft background music", "차분한 BGM 후보를 찾습니다."),
    ),
    "어두움": (
        ("dark ambience", "어두운 분위기 후보를 찾습니다."),
        ("eerie sound", "음산한 느낌의 후보를 찾습니다."),
    ),
    "귀여움": (
        ("cute game sfx", "귀여운 게임 효과음 후보를 찾습니다."),
        ("cartoon pop", "가벼운 만화풍 후보를 찾습니다."),
    ),
    "사이버/레트로": (
        ("8-bit sfx", "레트로 게임 효과음을 찾습니다."),
        ("chiptune loop", "칩튠 루프 후보를 찾습니다."),
        ("sci-fi ui", "SF UI 사운드 후보를 찾습니다."),
    ),
    "BGM": (
        ("background music", "BGM 후보를 일반 음악 검색어로 넓힙니다."),
        ("game music", "게임 음악 후보로 좁힙니다."),
    ),
    "루프": (
        ("seamless loop", "끊김 없는 반복 후보를 찾습니다."),
        ("loopable music", "반복 재생 가능한 음악 후보를 찾습니다."),
    ),
    "전투": (
        ("battle music", "전투 BGM 후보를 찾습니다."),
        ("combat loop", "전투 루프 후보를 찾습니다."),
    ),
    "긴장감": (
        ("suspense loop", "긴장감 있는 반복 후보를 찾습니다."),
        ("tension music", "긴장감 있는 음악 후보를 찾습니다."),
    ),
    "메뉴": (
        ("menu music", "메뉴 BGM 후보를 찾습니다."),
        ("menu select", "메뉴 선택음 후보를 찾습니다."),
    ),
    "보스전": (
        ("boss battle music", "보스전 BGM 후보를 찾습니다."),
        ("epic battle loop", "강한 전투 루프 후보를 찾습니다."),
    ),
}

NEGATIVE_SUGGESTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "잡음/환경음 제외": (
        ("clean isolated sfx", "잡음이 적은 분리 소스 표현으로 다시 찾습니다."),
        ("dry sound effect", "잔향과 배경이 적은 후보를 찾습니다."),
    ),
    "보컬/음성 제외": (
        ("instrumental loop", "보컬 없는 음악 후보에 가까운 표현입니다."),
        ("no vocals music", "보컬 제외 의도를 영어 검색어에 명확히 넣습니다."),
    ),
    "날카로움 제외": (
        ("soft ui click", "덜 날카로운 UI 사운드 후보를 찾습니다."),
        ("warm impact", "자극이 덜한 충격음 후보를 찾습니다."),
    ),
    "긴 사운드 제외": (
        ("short one-shot sfx", "짧은 효과음 후보를 명확히 찾습니다."),
        ("quick sound effect", "짧고 빠른 후보를 찾습니다."),
    ),
}

COMBINED_SUGGESTIONS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("검격", "묵직함"), "heavy sword slash", "검격에 묵직함을 더한 표현입니다."),
    (("검격", "깨끗한 소스"), "clean sword slash", "검격 후보 중 깨끗한 소스를 우선합니다."),
    (("검격", "날카로움 제외"), "soft blade whoosh", "검격을 덜 날카로운 휘두름으로 찾습니다."),
    (("마법", "묵직함"), "heavy magic impact", "마법 충격음을 묵직하게 좁힙니다."),
    (("마법", "어두움"), "dark magic impact", "어두운 마법 충격음으로 좁힙니다."),
    (("UI 클릭", "날카로움 제외"), "soft ui click", "덜 날카로운 UI 클릭음을 찾습니다."),
    (("UI 클릭", "깨끗한 소스"), "clean button click", "깨끗한 버튼 클릭 후보를 찾습니다."),
    (("BGM", "루프"), "seamless loop bgm", "BGM을 루프 후보 중심으로 좁힙니다."),
    (("BGM", "잔잔함"), "calm background music", "잔잔한 배경음악 후보를 찾습니다."),
    (("루프", "전투"), "battle loop", "전투 루프 후보를 찾습니다."),
)


def _dedupe(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return tuple(output)


def _dedupe_labels(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return tuple(output)


def _matches_any(text: str, compact_text: str, triggers: tuple[str, ...]) -> bool:
    return any(_matches_trigger(text, compact_text, trigger) for trigger in triggers)


def _matches_trigger(text: str, compact_text: str, trigger: str) -> bool:
    normalized = trigger.lower().strip()
    if not normalized:
        return False
    if re.fullmatch(r"[a-z0-9][a-z0-9 ._+&/-]*", normalized):
        return _matches_english_trigger(text, compact_text, normalized)
    return normalized in text or normalized.replace(" ", "") in compact_text


def _matches_english_trigger(text: str, compact_text: str, trigger: str) -> bool:
    pattern = rf"(?<![a-z0-9]){re.escape(trigger)}(?![a-z0-9])"
    if re.search(pattern, text):
        return True
    compact_trigger = re.sub(r"\s+", "", trigger)
    if compact_trigger == trigger:
        return False
    compact_pattern = rf"(?<![a-z0-9]){re.escape(compact_trigger)}(?![a-z0-9])"
    return bool(re.search(compact_pattern, compact_text))


def parse_prompt(prompt: str, use_interpretation: bool = True) -> ParsedPrompt:
    cleaned = " ".join(prompt.split())
    lowered = cleaned.lower()
    compact = re.sub(r"\s+", "", lowered)
    has_korean = bool(re.search(r"[가-힣]", cleaned))
    english_terms = tuple(
        word for word in re.findall(r"[a-z][a-z0-9_-]{1,}", lowered) if word not in ENGLISH_STOP_WORDS
    )

    if not use_interpretation:
        query = lowered if lowered else cleaned
        return ParsedPrompt(
            original=cleaned,
            query=query,
            include_terms=_dedupe(list(english_terms)),
        )

    terms: list[str] = []
    matched_concepts: list[str] = []
    negative_concepts: list[str] = []
    negative_terms: list[str] = []
    intent_flags: list[str] = []

    for rule in CONCEPT_RULES:
        if _matches_any(lowered, compact, rule.triggers):
            terms.extend(rule.terms)
            matched_concepts.extend(rule.concepts)
            intent_flags.extend(rule.intents)

    terms.extend(english_terms)

    for rule in NEGATIVE_RULES:
        if _matches_any(lowered, compact, rule.triggers):
            terms.extend(rule.query_terms)
            negative_terms.extend(rule.negative_terms)
            negative_concepts.extend(rule.concepts)
            intent_flags.extend(rule.intents)

    negative_set = set(_dedupe(list(negative_terms)))
    include_terms = tuple(term for term in _dedupe(terms) if term not in negative_set)
    query = " ".join(include_terms) if has_korean and include_terms else lowered

    suppressed_concepts = {
        concept
        for negative_concept in negative_concepts
        for concept in NEGATIVE_SUPPRESSED_CONCEPTS.get(negative_concept, ())
    }
    interpreted_concepts = [
        concept for concept in matched_concepts if has_korean and concept not in suppressed_concepts
    ]
    suggestion_concepts = [
        concept for concept in matched_concepts if concept not in suppressed_concepts
    ]
    fallback_queries: tuple[str, ...] = ()
    english_fallback = " ".join(_dedupe(list(english_terms)))
    if has_korean and english_fallback and english_fallback != query:
        fallback_queries = (english_fallback,)

    return ParsedPrompt(
        original=cleaned,
        query=query,
        include_terms=include_terms,
        interpreted_concepts=_dedupe_labels(interpreted_concepts),
        negative_concepts=_dedupe_labels(negative_concepts),
        negative_terms=tuple(sorted(negative_set)),
        intent_flags=_dedupe(intent_flags),
        fallback_queries=fallback_queries,
        suggestion_concepts=_dedupe_labels(suggestion_concepts),
    )


def build_search_suggestions(
    prompt_or_parsed: str | ParsedPrompt,
    *,
    limit: int = 4,
) -> tuple[PromptSuggestion, ...]:
    parsed = (
        prompt_or_parsed
        if isinstance(prompt_or_parsed, ParsedPrompt)
        else parse_prompt(prompt_or_parsed)
    )
    if not parsed.original or len(parsed.original.strip()) < 2:
        return ()
    if not (
        parsed.interpreted_concepts
        or parsed.negative_concepts
        or parsed.intent_flags
    ):
        return ()

    concepts = (
        *parsed.interpreted_concepts,
        *parsed.suggestion_concepts,
        *parsed.negative_concepts,
    )
    candidates: list[PromptSuggestion] = []
    concept_set = set(concepts)

    for required_concepts, prompt, reason in COMBINED_SUGGESTIONS:
        if all(concept in concept_set for concept in required_concepts):
            candidates.append(PromptSuggestion(label=prompt, prompt=prompt, reason=reason))

    for concept in _dedupe_labels([*parsed.interpreted_concepts, *parsed.suggestion_concepts]):
        for prompt, reason in CONCEPT_SUGGESTIONS.get(concept, ()):
            candidates.append(PromptSuggestion(label=prompt, prompt=prompt, reason=reason))

    for concept in parsed.negative_concepts:
        for prompt, reason in NEGATIVE_SUGGESTIONS.get(concept, ()):
            candidates.append(PromptSuggestion(label=prompt, prompt=prompt, reason=reason))

    return _dedupe_suggestions(candidates, parsed, limit)


def _dedupe_suggestions(
    suggestions: list[PromptSuggestion],
    parsed: ParsedPrompt,
    limit: int,
) -> tuple[PromptSuggestion, ...]:
    blocked = {
        _normalize_suggestion(parsed.original),
        _normalize_suggestion(parsed.query),
    }
    seen: set[str] = set()
    output: list[PromptSuggestion] = []
    for suggestion in suggestions:
        normalized = _normalize_suggestion(suggestion.prompt)
        if not normalized or normalized in blocked or normalized in seen:
            continue
        seen.add(normalized)
        output.append(suggestion)
        if len(output) >= max(0, limit):
            break
    return tuple(output)


def _normalize_suggestion(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w가-힣 -]+", " ", value.lower())).strip()
