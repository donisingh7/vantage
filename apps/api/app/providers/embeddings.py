import hashlib
import math
from typing import Any, Protocol

from app.core.exceptions import ProviderError


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...

    def embed_documents(self, documents: list[str]) -> list[list[float]]: ...

    def fingerprint(self) -> str:
        """Stable identifier for the provider + config that produces its vectors.

        Two calls return the same value iff embeddings from each are comparable
        (same provider, same model/deployment, same dimensionality). Used to decide
        whether a document's persisted index is still current after a provider or
        embedding-config change, not just after a content change.
        """
        ...


class AzureOpenAIEmbeddingProvider:
    """Real EmbeddingProvider backed by Azure OpenAI embeddings.

    Uses the synchronous SDK client so it matches the (deliberately sync) EmbeddingProvider
    Protocol without changing call sites; embedding calls are infrequent relative to request
    handling, so the brief blocking network call is an acceptable trade-off here.
    """

    def __init__(
        self, *, endpoint: str, api_key: str, api_version: str, embedding_deployment: str, dimensions: int | None = None
    ) -> None:
        from openai import AzureOpenAI

        self._client = AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)
        self._deployment = embedding_deployment
        self._dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        if not documents:
            return []
        from openai import OpenAIError

        kwargs: dict[str, Any] = {"model": self._deployment, "input": documents}
        if self._dimensions:
            kwargs["dimensions"] = self._dimensions
        try:
            response = self._client.embeddings.create(**kwargs)
        except OpenAIError as exc:
            raise ProviderError(f"Azure OpenAI embedding request failed ({type(exc).__name__})") from exc
        return [item.embedding for item in response.data]

    def fingerprint(self) -> str:
        dims = str(self._dimensions) if self._dimensions else "native"
        return f"azure_openai:{self._deployment}:dims={dims}"


class MockEmbeddingProvider:
    def __init__(self, dimensions: int = 32) -> None:
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        values: list[float] = []
        for index in range(self.dimensions):
            digest = hashlib.sha256(f"{index}:{text}".encode()).digest()
            values.append(int.from_bytes(digest[:4], "big") / 2**31 - 1)
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [self.embed_text(document) for document in documents]

    def fingerprint(self) -> str:
        return f"mock:dims={self.dimensions}"
