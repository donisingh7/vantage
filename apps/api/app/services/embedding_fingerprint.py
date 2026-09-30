"""Computes the *configured* embedding fingerprint straight from Settings.

DocumentIndexingService.is_current() compares a document's persisted
indexed_embedding_fingerprint against EmbeddingProvider.fingerprint() -- but that method
lives on a constructed provider instance, and constructing a real Gemini/Azure provider is
exactly the AI-client construction a read-only page (Intelligence bootstrap, documents list)
must not do just to display an "Indexed" badge.

The fingerprint format itself only ever depends on configuration (provider name + model/
deployment + dimensions), never on anything the live client would need to compute -- so this
mirrors each provider's fingerprint() format directly from Settings. If a provider's
fingerprint format in app/providers/embeddings.py ever changes, this must change with it;
that trade-off (a small, obvious duplication) is preferred here over constructing an AI
client on a read path.
"""
from app.core.config import Settings
from app.models import Document

_GEMINI_FINGERPRINT_VERSION = "retrieval-v1"


def configured_embedding_fingerprint(settings: Settings) -> str:
    if settings.embedding_provider == "mock":
        return f"mock:dims={settings.embedding_dimensions}"
    if settings.embedding_provider == "gemini":
        return f"gemini:{settings.gemini_embedding_model}:dims={settings.gemini_embedding_dimensions}:{_GEMINI_FINGERPRINT_VERSION}"
    dims = str(settings.azure_openai_embedding_dimensions) if settings.azure_openai_embedding_dimensions else "native"
    return f"azure_openai:{settings.azure_openai_embedding_deployment}:dims={dims}"


def document_is_indexed(document: Document, settings: Settings) -> bool:
    """Mirrors DocumentIndexingService.is_current() without constructing a provider."""
    return (
        document.content_hash is not None
        and document.indexed_content_hash == document.content_hash
        and document.indexed_embedding_fingerprint == configured_embedding_fingerprint(settings)
    )
