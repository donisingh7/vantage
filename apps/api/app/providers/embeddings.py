import hashlib
import math
from typing import Protocol


class EmbeddingProvider(Protocol):
    def embed_text(self, text: str) -> list[float]: ...

    def embed_documents(self, documents: list[str]) -> list[list[float]]: ...


class MockEmbeddingProvider:
    def __init__(self, dimensions: int = 32) -> None:
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least 8")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> list[float]:
        values: list[float] = []
        for index in range(self.dimensions):
            digest = hashlib.sha256(f"{index}:{text}".encode("utf-8")).digest()
            values.append(int.from_bytes(digest[:4], "big") / 2**31 - 1)
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed_documents(self, documents: list[str]) -> list[list[float]]:
        return [self.embed_text(document) for document in documents]
