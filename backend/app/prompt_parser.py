from __future__ import annotations

import re
from dataclasses import dataclass


KEYWORD_MAP: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("explosion", "boom", "impact", "blast", "폭발", "폭발음"), ("explosion", "boom", "impact")),
    (("magic", "spell", "magical", "마법", "주문"), ("magic", "spell", "fantasy")),
    (("dark", "shadow", "암흑", "어둠", "다크"), ("dark", "deep")),
    (("heavy", "bass", "묵직", "저음"), ("heavy", "low", "bass", "boom")),
    (("short", "짧", "원샷", "짧은"), ("short", "one-shot")),
    (("sharp", "날카", "쨍한"), ("sharp", "metallic")),
    (("sword", "slash", "blade", "검", "칼", "베기"), ("sword", "slash", "blade")),
    (("footstep", "발소리", "걸음"), ("footstep",)),
    (("button", "click", "버튼", "클릭"), ("button", "click", "ui")),
    (("wind", "바람"), ("wind",)),
    (("fire", "flame", "불", "화염"), ("fire", "flame")),
    (("water", "물", "물소리"), ("water",)),
    (("game", "게임", "효과음", "게임용", "sfx"), ("game", "sfx")),
    (("bgm", "브금", "배경음악", "루프", "loop"), ("bgm", "loop", "music")),
)


@dataclass(frozen=True)
class ParsedPrompt:
    original: str
    query: str
    include_terms: tuple[str, ...]


def _dedupe(items: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    output: list[str] = []
    for item in items:
        normalized = item.strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            output.append(normalized)
    return tuple(output)


def parse_prompt(prompt: str) -> ParsedPrompt:
    cleaned = " ".join(prompt.split())
    lowered = cleaned.lower()

    terms: list[str] = []
    for triggers, expansions in KEYWORD_MAP:
        if any(trigger in lowered for trigger in triggers):
            terms.extend(expansions)

    english_words = re.findall(r"[a-z][a-z0-9_-]{1,}", lowered)
    terms.extend(english_words)

    include_terms = _dedupe(terms)
    query = " ".join(include_terms) if include_terms else cleaned

    return ParsedPrompt(original=cleaned, query=query, include_terms=include_terms)
