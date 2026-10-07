"""OSM → `places` documents (MASTERSPEC §5.1, §7.2). Pure functions, used by the seed script."""

from datetime import datetime
from typing import Any

from app.models.enums import PlaceKind
from app.services.geo import cell5

BBox = tuple[float, float, float, float]  # south, west, north, east

# (tag key, value) → kind. `None` value means any value for that key.
_KIND_RULES: list[tuple[str, str | None, PlaceKind]] = [
    ("tourism", "museum", "museum"),
    ("amenity", "library", "library"),
    ("amenity", "cafe", "cafe"),
    ("amenity", "marketplace", "market"),
    ("tourism", "viewpoint", "viewpoint"),
    ("tourism", "artwork", "artwork"),
    ("leisure", "nature_reserve", "nature_reserve"),
    ("leisure", "garden", "garden"),
    ("leisure", "park", "park"),
    ("natural", "peak", "peak"),
    ("natural", "water", "water"),
    ("historic", None, "heritage"),
    ("natural", "wood", "other"),
    ("tourism", "attraction", "other"),
]
_INDOOR_KINDS: frozenset[PlaceKind] = frozenset({"museum", "library", "cafe"})
_SUMMARY_KEYS = (
    "tourism",
    "leisure",
    "natural",
    "historic",
    "amenity",
    "heritage",
    "cuisine",
    "artwork_type",
    "ele",
    "opening_hours",
    "wheelchair",
    "lit",
)
_BLOCKED_ACCESS = {"private", "no"}


def overpass_query(bbox: BBox, timeout_s: int = 90) -> str:
    s, w, n, e = bbox
    b = f"({s},{w},{n},{e})"
    return f"""[out:json][timeout:{timeout_s}];
(
  nwr["leisure"~"^(park|garden|nature_reserve)$"]["name"]{b};
  nwr["natural"~"^(peak|water|wood)$"]["name"]{b};
  nwr["tourism"~"^(viewpoint|artwork|attraction|museum)$"]["name"]{b};
  nwr["historic"]["name"]{b};
  nwr["amenity"~"^(marketplace|cafe|library)$"]["name"]{b};
);
out center tags;"""


def parse_bbox(raw: str) -> BBox:
    parts = [float(p) for p in raw.split(",")]
    if len(parts) != 4:
        raise ValueError("bbox must be 'S,W,N,E'")
    s, w, n, e = parts
    if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
        raise ValueError("bbox out of range or S>=N / W>=E")
    return s, w, n, e


def classify(tags: dict[str, str]) -> PlaceKind | None:
    for key, value, kind in _KIND_RULES:
        tag = tags.get(key)
        if tag is not None and (value is None or tag == value):
            return kind
    return None


def _coords(element: dict[str, Any]) -> tuple[float, float] | None:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    centre = element.get("center")
    if isinstance(centre, dict) and "lat" in centre and "lon" in centre:
        return float(centre["lat"]), float(centre["lon"])
    return None


def place_text(name: str, kind: PlaceKind, tags: dict[str, str]) -> str:
    """Short text that gets embedded for semantic search."""
    hints: list[str] = []
    for key in ("tourism", "leisure", "natural", "historic", "amenity", "heritage", "cuisine"):
        value = tags.get(key)
        if value and value not in ("yes", kind) and value not in hints:
            hints.append(value.replace("_", " ").replace(";", ", "))
    if tags.get("description"):
        hints.append(tags["description"][:120])
    return " — ".join(p for p in (name, kind.replace("_", " "), ", ".join(hints)) if p)


def place_from_osm(element: dict[str, Any], fetched_at: datetime) -> dict[str, Any] | None:
    """Map one Overpass element to a `places` doc (without embedding). None = skip."""
    tags: dict[str, str] = element.get("tags") or {}
    name = (tags.get("name:en") or tags.get("name") or "").strip()
    if not name or len(name) > 120:
        return None
    if tags.get("access") in _BLOCKED_ACCESS:
        return None
    kind = classify(tags)
    if kind is None:
        return None
    coords = _coords(element)
    if coords is None:
        return None
    lat, lng = coords
    indoor = kind in _INDOOR_KINDS or tags.get("indoor") == "yes"
    return {
        "_id": f"{element['type']}/{element['id']}",
        "name": name,
        "kind": kind,
        "tags_summary": "; ".join(f"{k}={tags[k]}" for k in _SUMMARY_KEYS if k in tags),
        "loc": {"type": "Point", "coordinates": [lng, lat]},
        "cell5": cell5(lat, lng),
        "indoor": indoor,
        "needs_daylight": not indoor and tags.get("lit") != "yes",
        "text": place_text(name, kind, tags),
        "source": "osm",
        "fetched_at": fetched_at,
    }


def places_from_overpass(payload: dict[str, Any], fetched_at: datetime) -> list[dict[str, Any]]:
    """Map + dedupe by _id (Overpass can return an element under several clauses)."""
    out: dict[str, dict[str, Any]] = {}
    for element in payload.get("elements", []):
        doc = place_from_osm(element, fetched_at)
        if doc is not None:
            out.setdefault(doc["_id"], doc)
    return list(out.values())
