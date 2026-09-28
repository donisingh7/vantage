from fastapi import APIRouter

from app.api.deps import AskServiceDep
from app.schemas.ask import AskCitationRead, AskRequest, AskResponse

router = APIRouter(tags=["ask"])


@router.post("/ask", response_model=AskResponse)
async def ask(payload: AskRequest, service: AskServiceDep) -> AskResponse:
    result = await service.ask(payload.question, top_k=payload.top_k)
    return AskResponse(
        answer=result.answer,
        citations=[
            AskCitationRead(
                document_id=citation.document_id, title=citation.title, source_name=citation.source_name,
                url=citation.url, excerpt=citation.excerpt, similarity=citation.similarity,
            )
            for citation in result.citations
        ],
        retrieved_count=result.retrieved_count,
        provider=result.provider,
        grounded=result.grounded,
    )
