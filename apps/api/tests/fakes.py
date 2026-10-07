"""Tiny in-memory stand-ins for PyMongo async collections and the embedder."""

from typing import Any

Doc = dict[str, Any]


class FakeCursor:
    def __init__(self, docs: list[Doc]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[Doc]:
        return list(self._docs if length is None else self._docs[:length])


class FakeCollection:
    def __init__(self, docs: list[Doc] | None = None, *, raise_exc: Exception | None = None):
        self.docs = docs or []
        self.pipelines: list[list[Doc]] = []
        self.raise_exc = raise_exc

    async def aggregate(self, pipeline: list[Doc]) -> FakeCursor:
        if self.raise_exc:
            raise self.raise_exc
        self.pipelines.append(pipeline)
        return FakeCursor(self.docs)


class FakeDB:
    def __init__(self, **collections: FakeCollection) -> None:
        self.collections = collections

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


class FakeEmbedder:
    """Deterministic 384-d vectors; records calls."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float((hash(t) % 7) + 1)] + [0.0] * 383 for t in texts]


def place_doc(pid: str, name: str, kind: str, lat: float, lng: float, **extra: Any) -> Doc:
    return {
        "_id": pid,
        "name": name,
        "kind": kind,
        "loc": {"type": "Point", "coordinates": [lng, lat]},
        "tags_summary": extra.pop("tags_summary", ""),
        "indoor": extra.pop("indoor", False),
        "needs_daylight": extra.pop("needs_daylight", True),
        "score": extra.pop("score", 0.9),
        **extra,
    }
