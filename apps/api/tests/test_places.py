from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError

from app.config import Settings
from app.deps import get_db, get_embedder_dep
from app.main import create_app
from app.services.embeddings import FastEmbedder, cosine
from app.services.geo import cells_around
from app.services.indexes import REGULAR_INDEXES, VECTOR_INDEXES
from app.services.places_repo import build_places_pipeline
from tests.fakes import FakeCollection, FakeDB, FakeEmbedder, place_doc

LAT, LNG = 18.520, 73.857


def _client(settings: Settings, db: Any, embedder: FakeEmbedder) -> TestClient:
    app = create_app(settings)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_embedder_dep] = lambda: embedder
    return TestClient(app)


def test_pipeline_shape() -> None:
    cells = cells_around(LAT, LNG)
    p = build_places_pipeline([0.1] * 384, cells, kinds=["park"])
    vs = p[0]["$vectorSearch"]
    assert vs["index"] == "places_vec" and vs["path"] == "embedding"
    assert vs["filter"] == {"$and": [{"cell5": {"$in": cells}}, {"kind": {"$in": ["park"]}}]}
    assert vs["numCandidates"] >= vs["limit"]
    assert p[1]["$project"]["score"] == {"$meta": "vectorSearchScore"}
    assert "embedding" not in p[1]["$project"]


def test_places_near_filters_by_radius_and_caps(settings: Settings, device_id: str) -> None:
    docs = [place_doc(f"node/{i}", f"Park {i}", "park", LAT + 0.001 * i, LNG) for i in range(12)]
    docs.append(place_doc("node/far", "Far Park", "park", LAT + 0.05, LNG))  # ~5.5 km
    db = FakeDB(places=FakeCollection(docs))
    emb = FakeEmbedder()
    res = _client(settings, db, emb).get(
        "/v1/places/near",
        params={"lat": 18.520449, "lng": 73.85678, "radius_m": 1000, "q": "Birds!!"},
        headers={"X-Device-Id": device_id},
    )
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 8
    assert all(c["distance_m"] <= 1000 for c in body)
    assert "node/far" not in {c["id"] for c in body}
    assert emb.calls == [["birds"]]
    # The pipeline used rounded coordinates' cells.
    vs = db["places"].pipelines[0][0]["$vectorSearch"]
    assert vs["filter"]["cell5"]["$in"] == cells_around(LAT, LNG)


def test_places_near_default_query(settings: Settings, device_id: str) -> None:
    emb = FakeEmbedder()
    res = _client(settings, FakeDB(), emb).get(
        "/v1/places/near", params={"lat": LAT, "lng": LNG}, headers={"X-Device-Id": device_id}
    )
    assert res.status_code == 200 and res.json() == []
    assert emb.calls == [["interesting public place to explore outdoors"]]


def test_places_near_db_error_is_503(settings: Settings, device_id: str) -> None:
    db = FakeDB(places=FakeCollection(raise_exc=ServerSelectionTimeoutError("x")))
    res = _client(settings, db, FakeEmbedder()).get(
        "/v1/places/near", params={"lat": LAT, "lng": LNG}, headers={"X-Device-Id": device_id}
    )
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "db_unavailable"


def test_places_near_requires_device_and_valid_params(settings: Settings, device_id: str) -> None:
    client = _client(settings, FakeDB(), FakeEmbedder())
    assert client.get("/v1/places/near", params={"lat": LAT, "lng": LNG}).status_code == 400
    res = client.get(
        "/v1/places/near",
        params={"lat": LAT, "lng": LNG, "radius_m": 99999},
        headers={"X-Device-Id": device_id},
    )
    assert res.status_code == 422


def test_places_near_without_mongo_is_503(settings: Settings, device_id: str) -> None:
    app = create_app(settings)  # no MONGODB_URI, no override
    res = TestClient(app).get(
        "/v1/places/near", params={"lat": LAT, "lng": LNG}, headers={"X-Device-Id": device_id}
    )
    assert res.status_code == 503


def test_healthz_reports_unknown_when_unconfigured(settings: Settings) -> None:
    body = TestClient(create_app(settings)).get("/healthz").json()
    assert body == {"status": "ok", "db": "unknown", "llm": "unknown"}


def test_healthz_reports_llm_down(device_id: str) -> None:
    s = Settings(env="test", llm_base_url="http://127.0.0.1:9")  # nothing listens on port 9
    assert TestClient(create_app(s)).get("/healthz").json()["llm"] == "down"


def test_index_definitions_match_spec() -> None:
    name, places = VECTOR_INDEXES["places"]
    assert name == "places_vec"
    vec = places["fields"][0]
    assert (vec["numDimensions"], vec["similarity"], vec["path"]) == (384, "cosine", "embedding")
    assert {f["path"] for f in places["fields"][1:]} == {"cell5", "kind"}
    mem_name, mem = VECTOR_INDEXES["memories"]
    assert mem_name == "memories_vec"
    assert {f["path"] for f in mem["fields"][1:]} == {"device_id", "ts"}
    ttl = [i for i in REGULAR_INDEXES["memories"] if i.document.get("expireAfterSeconds")]
    assert ttl and ttl[0].document["expireAfterSeconds"] == 90 * 24 * 3600
    unique = [i for i in REGULAR_INDEXES["completions"] if i.document.get("unique")]
    assert unique[0].document["key"] == {"quest_id": 1}


class _FakeModel:
    def __init__(self) -> None:
        self.calls = 0

    def embed(self, texts: list[str], batch_size: int) -> Any:
        self.calls += 1
        for t in texts:
            yield [float(len(t))] * 384


async def test_fastembedder_wrapper_batches_and_converts() -> None:
    emb = FastEmbedder("BAAI/bge-small-en-v1.5")
    fake = _FakeModel()
    emb._model = fake  # skip the real ONNX download
    out = await emb.embed(["ab", "abcd"])
    assert [v[0] for v in out] == [2.0, 4.0]
    assert all(len(v) == 384 and isinstance(v[0], float) for v in out)
    assert await emb.embed([]) == []
    assert fake.calls == 1


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [([1, 0], [1, 0], 1.0), ([1, 0], [0, 1], 0.0), ([1, 0], [-1, 0], -1.0), ([0, 0], [1, 0], 0.0)],
)
def test_cosine(a: list[float], b: list[float], expected: float) -> None:
    assert cosine(a, b) == pytest.approx(expected)
