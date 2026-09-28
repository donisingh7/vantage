from uuid import UUID

from fastapi import APIRouter, Query, status

from app.api.deps import IndexingServiceDep, IngestionServiceDep, IntelligenceAnalysisServiceDep
from app.schemas.common import ListResponse
from app.schemas.ingestion import DocumentRead
from app.schemas.intelligence import IntelligenceSignalRead
from app.schemas.search import IndexResultRead

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("", response_model=ListResponse[DocumentRead])
async def list_documents(
    service: IngestionServiceDep,
    analysis: IntelligenceAnalysisServiceDep,
    indexing: IndexingServiceDep,
    source_id: UUID | None = Query(default=None),
) -> ListResponse[DocumentRead]:
    documents = await service.list_documents(source_id)
    signals = await analysis.signals_by_document([document.id for document in documents])
    items = [
        DocumentRead.model_validate(document).model_copy(
            update={
                "analysis_status": signals[document.id].analysis_status.value if document.id in signals else None,
                "signal_id": signals[document.id].id if document.id in signals else None,
                "indexed": indexing.is_current(document),
            }
        )
        for document in documents
    ]
    return ListResponse(items=items, total=len(items))


@router.post("/{document_id}/analyze", response_model=IntelligenceSignalRead, status_code=status.HTTP_201_CREATED)
async def analyze_document(
    document_id: UUID, service: IntelligenceAnalysisServiceDep, force: bool = Query(default=False)
) -> IntelligenceSignalRead:
    signal = await service.analyze_document(document_id, force=force)
    return IntelligenceSignalRead.model_validate(signal)


@router.post("/{document_id}/index", response_model=IndexResultRead, status_code=status.HTTP_201_CREATED)
async def index_document(
    document_id: UUID, service: IndexingServiceDep, force: bool = Query(default=False)
) -> IndexResultRead:
    result = await service.index_document(document_id, force=force)
    return IndexResultRead(
        document_id=result.document_id, chunks_created=result.chunks_created,
        total_chunks=result.total_chunks, skipped=result.skipped,
    )
