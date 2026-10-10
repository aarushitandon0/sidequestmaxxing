"""Event schemas (P23 spec section 4, section 6).

`SerpEvent` is the raw SerpApi entry, validated at the boundary. `EventDoc` is what the
`events` collection stores: no `description` field exists anywhere on it, so the longest piece
of untrusted prose can never be surfaced by a later change (spec section 6).
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import PlaceKind

Geocode = Literal["place_match", "nominatim"]


class SerpEvent(BaseModel):
    """One `events_results[]` entry, after validation. Every string here is untrusted."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1)
    venue_name: str = ""
    address: list[str] = Field(default_factory=list)
    url: str | None = None
    when_text: str = ""
    start_date: str = ""
    description: str = ""


class EventDoc(BaseModel):
    """A stored `events` document. Serialize with `by_alias=True` for the `_id` key."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    id: str = Field(alias="_id")
    name: str
    kind: PlaceKind
    venue_name: str
    tags_summary: str
    loc: dict[str, Any]
    cell5: str
    indoor: bool
    needs_daylight: bool
    starts_at: datetime
    ends_at: datetime
    when_text: str
    url: str | None
    place_id: str | None
    geocode: Geocode
    text: str
    embedding: list[float]
    source: str = "serpapi"
    fetched_at: datetime
