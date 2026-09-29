import hashlib
import json
import re
from enum import Enum
from types import UnionType
from typing import Any, Literal, Protocol, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from app.core.exceptions import ProviderError

# A real provider (e.g. Azure OpenAI) implements this same Protocol; nothing else
# in this module or its callers needs to change for that to plug in later.


class LLMProvider(Protocol):
    async def generate(self, prompt: str, *, system: str | None = None) -> str: ...

    async def structured_generate(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any: ...


class AzureOpenAILLMProvider:
    """Real LLMProvider backed by Azure OpenAI chat completions.

    Structured output is requested via JSON-mode plus an inline JSON Schema in the
    system prompt (broadly compatible across Azure OpenAI API versions/deployments),
    then validated locally with the caller's Pydantic schema before use.
    """

    def __init__(self, *, endpoint: str, api_key: str, api_version: str, chat_deployment: str) -> None:
        from openai import AsyncAzureOpenAI

        self._client = AsyncAzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        self._deployment = chat_deployment

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._request(messages=messages)
        return (response.choices[0].message.content or "").strip()

    async def structured_generate(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any:
        schema_json = schema.model_json_schema() if issubclass(schema, BaseModel) else {}
        instructions = (
            f"{system}\n\n" if system else ""
        ) + (
            "Respond with ONLY a single valid JSON object matching this JSON Schema. "
            "No prose, no markdown code fences.\n"
            f"JSON Schema: {json.dumps(schema_json)}"
        )
        messages = [{"role": "system", "content": instructions}, {"role": "user", "content": prompt}]
        response = await self._request(messages=messages, response_format={"type": "json_object"})
        content = response.choices[0].message.content or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError("Azure OpenAI returned a response that was not valid JSON") from exc
        return schema.model_validate(parsed)

    async def _request(self, **kwargs: Any) -> Any:
        from openai import OpenAIError

        try:
            return await self._client.chat.completions.create(model=self._deployment, **kwargs)
        except OpenAIError as exc:
            # Never surface the raw SDK exception: it can echo request details back to the client.
            raise ProviderError(f"Azure OpenAI request failed ({type(exc).__name__})") from exc


class GeminiLLMProvider:
    """Real LLMProvider backed by Google's Gemini API via the official `google-genai` SDK.

    Structured output uses the SDK's own response_mime_type="application/json" +
    response_schema support, but the returned text is still independently re-validated
    through the caller's Pydantic schema below -- the SDK's own parsing is never trusted
    as-is.
    """

    def __init__(self, *, api_key: str, model: str) -> None:
        from google import genai

        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        from google.genai import types

        config = types.GenerateContentConfig(system_instruction=system) if system else None
        response = await self._request(contents=prompt, config=config)
        return (response.text or "").strip()

    async def structured_generate(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any:
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system, response_mime_type="application/json", response_schema=schema
        )
        response = await self._request(contents=prompt, config=config)
        content = response.text or "{}"
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError("Gemini returned a response that was not valid JSON") from exc
        return schema.model_validate(parsed)

    async def _request(self, *, contents: str, config: Any) -> Any:
        from google.genai import errors as genai_errors

        try:
            return await self._client.aio.models.generate_content(model=self._model, contents=contents, config=config)
        except genai_errors.APIError as exc:
            # Never surface the raw SDK exception: it can echo request details back to the client.
            raise ProviderError(f"Gemini request failed ({type(exc).__name__})") from exc


# Field names of the document-analysis structured-output contract (see
# app.services.analysis_schema.DocumentAnalysisResult). Matched by name only, so this
# provider never has to import that service-layer schema.
_DOCUMENT_ANALYSIS_FIELDS = frozenset(
    {
        "relevant",
        "relevance_score",
        "signal_type",
        "title",
        "executive_summary",
        "importance_score",
        "sentiment",
        "key_entities",
        "key_points",
        "business_impact",
        "confidence_score",
        "evidence_excerpt",
    }
)

_SIGNAL_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("funding", ("raised", "funding", "series a", "series b", "series c", "investment", "venture")),
    ("acquisition", ("acquire", "acquisition", "acquired", "merger")),
    ("partnership", ("partnership", "partners with", "collaborat")),
    ("leadership", ("appoint", " ceo", " cfo", " cto", "hires", "executive")),
    ("regulation", ("regulat", "compliance", "lawsuit", "antitrust", "policy")),
    ("pricing", ("pricing", "price increase", "discount")),
    ("product", ("launch", "release", "unveil", "announc")),
    ("technology", (" ai ", "platform", "infrastructure", "cloud", "technology")),
    ("competitor", ("competitor", "rival")),
    ("market", ("market", "industry", "sector")),
    ("risk", ("risk", "breach", "delay", "warning", "recall")),
]
_NEGATIVE_KEYWORDS = ("lawsuit", "breach", "delay", "recall", "risk", "decline", "warning", "layoff")
_POSITIVE_KEYWORDS = ("launch", "growth", "raise", "raised", "partnership", "award", "record")
_STOPWORDS = {"the", "and", "for", "with", "this", "that", "from", "have", "will"}


def _parse_marked_section(prompt: str, key: str) -> str:
    marker = f"{key}:"
    if marker not in prompt:
        return ""
    after = prompt.split(marker, 1)[1]
    for stop in ("\nSOURCE_URL:", "\nTITLE:", "\nCONTENT:", "\n### END OF UNTRUSTED DOCUMENT ###"):
        if stop in after:
            after = after.split(stop, 1)[0]
    return after.strip()


def _stable_unit_score(seed: str) -> float:
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def _classify_signal_type(text: str) -> str:
    lowered = f" {text.lower()} "
    for signal_type, keywords in _SIGNAL_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return signal_type
    return "other"


def _classify_sentiment(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in _NEGATIVE_KEYWORDS):
        return "negative"
    if any(word in lowered for word in _POSITIVE_KEYWORDS):
        return "positive"
    return "neutral"


def _extract_naive_entities(text: str) -> list[str]:
    words = re.findall(r"\b[A-Z][a-zA-Z0-9&]{2,}\b", text)
    entities: list[str] = []
    for word in words:
        if word not in entities and word.lower() not in _STOPWORDS:
            entities.append(word)
        if len(entities) >= 5:
            break
    return entities


MIN_RELEVANT_CONTENT_CHARS = 40


def _mock_document_analysis(prompt: str) -> dict[str, Any]:
    """Deterministic, content-derived mock analysis. Never a substitute for real AI review.

    Relevance is content-length gated: a document with little or no body text cannot be
    real market intelligence, so it is deterministically marked irrelevant.
    """
    title = _parse_marked_section(prompt, "TITLE") or "Untitled document"
    content = _parse_marked_section(prompt, "CONTENT")
    basis = f"{title}\n{content}".strip()
    excerpt_source = content.strip() or title

    relevant = len(content.strip()) >= MIN_RELEVANT_CONTENT_CHARS
    relevance_unit = _stable_unit_score(basis + "relevance")
    relevance_score = round((0.6 + 0.35 * relevance_unit) if relevant else (0.35 * relevance_unit), 2)
    signal_type = _classify_signal_type(basis) if relevant else "other"
    importance_score = round(0.2 + 0.7 * _stable_unit_score(basis + "importance"), 2) if relevant else 0.0
    confidence_score = round(0.5 + 0.4 * _stable_unit_score(basis + "confidence"), 2)

    return {
        "relevant": relevant,
        "relevance_score": relevance_score,
        "signal_type": signal_type,
        "title": f"Mock signal: {title[:80]}" if relevant else title[:80],
        "executive_summary": f"Mock analysis: {title}. {excerpt_source[:160]}".strip()[:500] or "Mock analysis: no content.",
        "importance_score": importance_score,
        "sentiment": _classify_sentiment(basis),
        "key_entities": _extract_naive_entities(basis),
        "key_points": [f"Mock key point derived from: {title[:60]}"] if title else [],
        "business_impact": f"Mock business impact assessment for a {signal_type} signal. No real AI model was called.",
        "confidence_score": confidence_score,
        "evidence_excerpt": excerpt_source[:220] or "No excerpt available.",
    }


def _extract_after_marker(prompt: str, marker: str) -> str:
    if marker not in prompt:
        return ""
    after = prompt.split(marker, 1)[1]
    return after.split("\n\n", 1)[0].strip()


def _mock_ask_answer(prompt: str) -> str:
    """Deterministic Ask Vantage mock answer, grounded only in the [Source N] blocks present."""
    question = _extract_after_marker(prompt, "QUESTION:") or "your question"
    source_numbers = sorted({int(n) for n in re.findall(r"\[Source (\d+)\]", prompt)})
    citation_text = ", ".join(f"[Source {n}]" for n in source_numbers) if source_numbers else "the retrieved context"
    return (
        f'Mock answer: based on {citation_text}, here is a development-mode summary relevant to '
        f'"{question}". This is deterministic mock output; no external AI model was called.'
    )


class MockLLMProvider:
    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        if "QUESTION:" in prompt and "[Source" in prompt:
            return _mock_ask_answer(prompt)
        subject = " ".join(prompt.split())[:240] or "the supplied request"
        return f"Mock analysis: Review {subject}. No external model was called."

    async def structured_generate(self, prompt: str, schema: type[Any], *, system: str | None = None) -> Any:
        if issubclass(schema, BaseModel):
            if set(schema.model_fields) == _DOCUMENT_ANALYSIS_FIELDS:
                return schema.model_validate(_mock_document_analysis(prompt))
            values: dict[str, Any] = {}
            for name, field in schema.model_fields.items():
                if not field.is_required():
                    values[name] = field.get_default(call_default_factory=True)
                else:
                    values[name] = _mock_field_value(name, field)
            return schema.model_validate(values)
        return schema()


def _mock_field_value(name: str, field: FieldInfo) -> Any:
    annotation = field.annotation
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        options = [option for option in get_args(annotation) if option is not type(None)]
        return _mock_field_value(name, FieldInfo(annotation=options[0])) if options else None
    if origin is Literal:
        return get_args(annotation)[0]
    field_type = origin or annotation
    if field_type is str:
        return f"Mock {name.replace('_', ' ')}"
    if field_type is bool:
        return False
    if field_type is int:
        return 0
    if field_type is float:
        return 0.0
    if field_type is list:
        return []
    if field_type is dict:
        return {}
    if isinstance(field_type, type) and issubclass(field_type, Enum):
        return next(iter(field_type)).value
    if isinstance(field_type, type) and issubclass(field_type, BaseModel):
        nested_values = {
            nested_name: nested_field.get_default(call_default_factory=True)
            if not nested_field.is_required()
            else _mock_field_value(nested_name, nested_field)
            for nested_name, nested_field in field_type.model_fields.items()
        }
        return field_type.model_validate(nested_values)
    return None
