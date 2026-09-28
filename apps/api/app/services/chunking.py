"""Deterministic, overlap-aware text chunking. Same input always yields the same chunks."""

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 100


def chunk_text(text: str, *, chunk_size: int = DEFAULT_CHUNK_SIZE, overlap: int = DEFAULT_OVERLAP) -> list[str]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []
    if chunk_size <= 0:
        return [cleaned]

    step = max(1, chunk_size - max(0, overlap))
    chunks: list[str] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start += step
    return chunks
