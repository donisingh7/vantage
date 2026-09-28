"""Ask Vantage: question -> semantic retrieval -> grounded LLM answer -> citations.

Citations always come from the server-side retrieved chunks; the model is never
trusted to invent its own source list.
"""
from dataclasses import dataclass
from uuid import UUID

from app.providers.llm import LLMProvider
from app.services.ask_prompts import ASK_SYSTEM_PROMPT, build_ask_prompt
from app.services.semantic_search import SemanticSearchService

NO_EVIDENCE_ANSWER = (
    "There is not enough evidence in your collected intelligence to answer this yet. "
    "Try ingesting and indexing more sources, then ask again."
)


@dataclass
class AskCitation:
    document_id: UUID
    title: str | None
    source_name: str
    url: str
    excerpt: str
    similarity: float


@dataclass
class AskResult:
    answer: str
    citations: list[AskCitation]
    retrieved_count: int
    provider: str
    grounded: bool


class AskVantageService:
    def __init__(
        self, search: SemanticSearchService, llm: LLMProvider, *, provider_name: str
    ) -> None:
        self.search = search
        self.llm = llm
        self.provider_name = provider_name

    async def ask(self, question: str, *, top_k: int = 5) -> AskResult:
        results = await self.search.search(question, top_k=top_k)
        if not results:
            return AskResult(
                answer=NO_EVIDENCE_ANSWER, citations=[], retrieved_count=0,
                provider=self.provider_name, grounded=False,
            )

        prompt = build_ask_prompt(question=question, results=results)
        answer = await self.llm.generate(prompt, system=ASK_SYSTEM_PROMPT)

        citations = [
            AskCitation(
                document_id=result.document_id,
                title=result.title,
                source_name=result.source_name,
                url=result.canonical_url,
                excerpt=result.excerpt,
                similarity=result.similarity,
            )
            for result in results
        ]
        return AskResult(
            answer=answer, citations=citations, retrieved_count=len(results),
            provider=self.provider_name, grounded=True,
        )
