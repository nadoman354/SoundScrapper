from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.app.config import Settings
from backend.app.schemas import AISearchAssistRequest, SearchSuggestion


class LocalAIError(RuntimeError):
    """Raised when the optional local AI assistant cannot return a usable response."""


@dataclass(frozen=True)
class LocalAIStatus:
    reachable: bool
    message: str


@dataclass(frozen=True)
class LocalAISearchAssist:
    primary_query: str
    alternative_queries: list[SearchSuggestion] = field(default_factory=list)
    translated_intent: str = ""
    intent_label: str = ""
    sound_type: str = "unknown"
    preferred_duration: str = ""
    avoid_concepts: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    deprioritize_sources: list[str] = field(default_factory=list)
    confidence: float = 0.0
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class LocalAIClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    async def status(self) -> LocalAIStatus:
        try:
            async with self._client() as client:
                response = await client.get("/v1/models")
                response.raise_for_status()
        except httpx.HTTPError as exc:
            return LocalAIStatus(False, f"로컬 AI 서버 응답 없음: {exc}")
        return LocalAIStatus(True, "로컬 AI 서버 연결됨")

    async def suggest(self, request: AISearchAssistRequest) -> LocalAISearchAssist:
        payload = {
            "model": self.model,
            "temperature": 0.2,
            "max_tokens": 750,
            "messages": [
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": _user_prompt(request),
                },
            ],
        }
        try:
            async with self._client() as client:
                response = await client.post("/v1/chat/completions", json=payload)
                response.raise_for_status()
                body = response.json()
        except httpx.HTTPError as exc:
            raise LocalAIError(f"로컬 AI 요청 실패: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LocalAIError("로컬 AI 응답을 JSON으로 읽지 못했습니다.") from exc

        content = _extract_message_content(body)
        parsed = _parse_json_object(content)
        return _normalize_assist(parsed, request.prompt)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout_seconds,
            transport=self.transport,
        )


def make_local_ai_client(settings: Settings) -> LocalAIClient:
    return LocalAIClient(
        base_url=settings.ai_base_url,
        model=settings.ai_model,
        timeout_seconds=settings.ai_timeout_seconds,
    )


_SYSTEM_PROMPT = """You help a game sound designer search public audio libraries.
Return ONLY a compact JSON object with these keys:
intent_label: short Korean label for the sound the user likely wants.
sound_type: one of sfx, bgm, ambience, music, unknown.
primary_queries: array of 1-4 broad English search queries.
primary_query: the best single English query, same as primary_queries[0].
alternative_queries: array of up to 4 objects with prompt, label, reason.
avoid_concepts: array of concepts that likely pollute results.
preferred_duration: short, medium, long, loop, any, or unknown.
preferred_sources: array using freesound, openverse, jamendo when useful.
deprioritize_sources: array using freesound, openverse, jamendo when useful.
translated_intent: one short Korean sentence.
confidence: number from 0 to 1.
notes: up to 3 short Korean notes.
warnings: up to 2 short Korean warnings.

Rules:
- You are an intent profiler, not a result filter. Never say candidates should be removed.
- The app will only show your profile and let the user choose a query.
- behavior_profile is a compact local summary of the user's recent searches, listens, saves,
  and skips. Use it only as a weak hint; do not override the current prompt.
- For game SFX searches, prefer concrete sound-event terms over genre/music terms.
- Ambiguous words must be disambiguated for sound-library search purity.
- Example: "electric" in a short game-SFX context should mean electric zap/spark/crackle,
  and avoid electronic music, synth, electric guitar, EDM, song, melody.
- Example: "drum" with short duration should mean drum hit/kick/snare/percussion one-shot,
  not a full song unless loop/BGM/music is requested.
- Preserve precise SFX words such as slash, hit, click, whoosh as broad primary queries.
- Do not over-specify license, exact duration, quality, or game-readiness in the query.
- Keep queries broad enough for exploration.
- No markdown. No explanations outside JSON."""


def _user_prompt(request: AISearchAssistRequest) -> str:
    return json.dumps(
        {
            "prompt": request.prompt,
            "source_filter": request.source_filter,
            "license": request.license,
            "min_duration": request.min_duration,
            "max_duration": request.max_duration,
            "behavior_profile": request.behavior_profile,
        },
        ensure_ascii=False,
    )


def _extract_message_content(body: dict[str, Any]) -> str:
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LocalAIError("로컬 AI 응답 형식이 예상과 다릅니다.") from exc
    if not isinstance(content, str) or not content.strip():
        raise LocalAIError("로컬 AI 응답이 비어 있습니다.")
    return content.strip()


def _parse_json_object(content: str) -> dict[str, Any]:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if not match:
            raise LocalAIError("로컬 AI 응답에서 JSON 객체를 찾지 못했습니다.")
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LocalAIError("로컬 AI JSON 응답 파싱에 실패했습니다.") from exc
    if not isinstance(value, dict):
        raise LocalAIError("로컬 AI 응답이 JSON 객체가 아닙니다.")
    return value


def _normalize_assist(data: dict[str, Any], original_prompt: str) -> LocalAISearchAssist:
    primary_queries = _query_list(data.get("primary_queries"))
    primary_query = (
        primary_queries[0]
        if primary_queries
        else _safe_query(data.get("primary_query")) or original_prompt.strip()
    )
    alternatives: list[SearchSuggestion] = []
    for prompt in primary_queries[1:4]:
        alternatives.append(
            SearchSuggestion(
                label=prompt,
                prompt=prompt,
                reason="AI가 같은 의도에서 제안한 대체 검색식입니다.",
            )
        )
    for raw in _as_list(data.get("alternative_queries"))[:4]:
        if not isinstance(raw, dict):
            continue
        prompt = _safe_query(raw.get("prompt"))
        if not prompt or prompt.lower() == primary_query.lower():
            continue
        label = _safe_label(raw.get("label")) or prompt
        reason = _safe_label(raw.get("reason"))
        alternatives.append(SearchSuggestion(label=label, prompt=prompt, reason=reason))

    notes = [_safe_label(item) for item in _as_list(data.get("notes"))]
    warnings = [_safe_label(item) for item in _as_list(data.get("warnings"))]
    return LocalAISearchAssist(
        primary_query=primary_query,
        alternative_queries=alternatives,
        translated_intent=_safe_label(data.get("translated_intent")),
        intent_label=_safe_label(data.get("intent_label")),
        sound_type=_safe_sound_type(data.get("sound_type")),
        preferred_duration=_safe_duration(data.get("preferred_duration")),
        avoid_concepts=_safe_label_list(data.get("avoid_concepts"), 8),
        preferred_sources=_safe_source_list(data.get("preferred_sources")),
        deprioritize_sources=_safe_source_list(data.get("deprioritize_sources")),
        confidence=_safe_confidence(data.get("confidence")),
        notes=[item for item in notes if item][:3],
        warnings=[item for item in warnings if item][:3],
    )


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _query_list(value: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(value):
        query = _safe_query(raw)
        normalized = query.lower()
        if query and normalized not in seen:
            seen.add(normalized)
            output.append(query)
    return output[:4]


def _safe_label_list(value: Any, limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in _as_list(value):
        label = _safe_label(raw)
        normalized = label.lower()
        if label and normalized not in seen:
            seen.add(normalized)
            output.append(label)
        if len(output) >= limit:
            break
    return output


def _safe_source_list(value: Any) -> list[str]:
    allowed = {"freesound", "openverse", "jamendo"}
    output: list[str] = []
    for raw in _as_list(value):
        source = str(raw or "").strip().lower()
        if source in allowed and source not in output:
            output.append(source)
    return output


def _safe_sound_type(value: Any) -> str:
    sound_type = str(value or "").strip().lower()
    return sound_type if sound_type in {"sfx", "bgm", "ambience", "music", "unknown"} else "unknown"


def _safe_duration(value: Any) -> str:
    duration = str(value or "").strip().lower()
    return duration if duration in {"short", "medium", "long", "loop", "any", "unknown"} else "unknown"


def _safe_confidence(value: Any) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, confidence))


def _safe_query(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w가-힣 .,'+&/-]+", "", text)
    return text[:120].strip()


def _safe_label(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)
    return text[:160].strip()
