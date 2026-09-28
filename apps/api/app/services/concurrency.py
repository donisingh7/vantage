"""Tiny in-process guard against overlapping async operations on the same key.

Single-process only, matching this project's non-distributed scheduling design.
Not a substitute for a real distributed lock if this ever runs multi-process.
"""
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager

from app.core.exceptions import ConflictError


class InProcessKeyGuard:
    def __init__(self, *, conflict_message: str) -> None:
        self._active: set[Hashable] = set()
        self._conflict_message = conflict_message

    @asynccontextmanager
    async def acquire(self, key: Hashable) -> AsyncIterator[None]:
        if key in self._active:
            raise ConflictError(self._conflict_message)
        self._active.add(key)
        try:
            yield
        finally:
            self._active.discard(key)
