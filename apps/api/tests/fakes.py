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
        return self.collections.setdefault(name, MemCollection())


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


# --- A small in-memory Mongo collection for CRUD-style tests ----------------------------------


def _get_path(doc: Doc, path: str) -> Any:
    cur: Any = doc
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _matches(doc: Doc, flt: Doc) -> bool:
    for key, cond in flt.items():
        if key == "$and":
            if not all(_matches(doc, c) for c in cond):
                return False
            continue
        value = _get_path(doc, key)
        if isinstance(cond, dict) and any(k.startswith("$") for k in cond):
            for op, arg in cond.items():
                ok = {
                    "$eq": lambda v, a: v == a,
                    "$ne": lambda v, a: v != a,
                    "$in": lambda v, a: v in a,
                    "$gte": lambda v, a: v is not None and v >= a,
                    "$gt": lambda v, a: v is not None and v > a,
                    "$lt": lambda v, a: v is not None and v < a,
                    "$lte": lambda v, a: v is not None and v <= a,
                }[op](value, arg)
                if not ok:
                    return False
        elif value != cond:
            return False
    return True


class _Result:
    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)


class MemCollection(FakeCollection):
    """Supports the subset of PyMongo async calls the API uses. Raises if `fail` is set."""

    def __init__(self, docs: list[Doc] | None = None, *, fail: Exception | None = None):
        super().__init__(docs, raise_exc=fail)
        self.fail = fail

    def _check(self) -> None:
        if self.fail:
            raise self.fail

    async def insert_one(self, doc: Doc) -> _Result:
        self._check()
        from pymongo.errors import DuplicateKeyError

        if "_id" in doc and any(d.get("_id") == doc["_id"] for d in self.docs):
            raise DuplicateKeyError("duplicate _id")
        self.docs.append(dict(doc))
        return _Result(inserted_id=doc.get("_id"))

    async def find_one(self, flt: Doc, *a: Any, **kw: Any) -> Doc | None:
        self._check()
        return next((dict(d) for d in self.docs if _matches(d, flt)), None)

    def find(self, flt: Doc | None = None, *a: Any, **kw: Any) -> "MemCursor":
        self._check()
        return MemCursor([dict(d) for d in self.docs if _matches(d, flt or {})])

    async def count_documents(self, flt: Doc) -> int:
        self._check()
        return sum(_matches(d, flt) for d in self.docs)

    def _apply(self, doc: Doc, update: Doc) -> None:
        for key, value in update.get("$set", {}).items():
            doc[key] = value
        for key, value in update.get("$inc", {}).items():
            doc[key] = doc.get(key, 0) + value
        for key, value in update.get("$setOnInsert", {}).items():
            doc.setdefault(key, value)

    async def find_one_and_update(self, flt: Doc, update: Doc, **kw: Any) -> Doc | None:
        self._check()
        for d in self.docs:
            if _matches(d, flt):
                self._apply(d, update)
                return dict(d)
        return None

    async def update_one(self, flt: Doc, update: Doc, upsert: bool = False) -> _Result:
        self._check()
        for d in self.docs:
            if _matches(d, flt):
                self._apply(d, update)
                return _Result(matched_count=1, upserted_id=None)
        if upsert:
            new = {k: v for k, v in flt.items() if not k.startswith("$")}
            self._apply(new, update)
            self.docs.append(new)
            return _Result(matched_count=0, upserted_id=new.get("_id"))
        return _Result(matched_count=0, upserted_id=None)

    async def delete_many(self, flt: Doc) -> _Result:
        self._check()
        before = len(self.docs)
        self.docs = [d for d in self.docs if not _matches(d, flt)]
        return _Result(deleted_count=before - len(self.docs))


class MemCursor:
    def __init__(self, docs: list[Doc]) -> None:
        self.docs = docs

    def sort(self, key: str, direction: int = 1) -> "MemCursor":
        self.docs.sort(key=lambda d: _get_path(d, key), reverse=direction < 0)
        return self

    def limit(self, n: int) -> "MemCursor":
        self.docs = self.docs[:n]
        return self

    async def to_list(self, length: int | None = None) -> list[Doc]:
        return list(self.docs if length is None else self.docs[:length])
