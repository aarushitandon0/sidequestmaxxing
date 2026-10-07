"""Builders for quest dicts and candidates used across validator tests."""

import copy
from typing import Any

from app.services.places_repo import Candidate

BASE_QUEST: dict[str, Any] = {
    "title": "The Banyan Oracle",
    "category": "naturalist",
    "briefing": "Walk to the old banyan in Banyan Park and count its hanging roots before sunset.",
    "objective": "Find the biggest banyan in the park and photograph its roots.",
    "place_id": "way/2",
    "est_minutes": 30,
    "verification": {"method": "photo", "photo_prompt": "banyan tree aerial roots"},
    "safety_note": "Stay on paths and keep to daylight.",
    "off_screen_tip": "Phone in pocket until you reach the tree.",
}

PARK = Candidate(id="way/2", name="Banyan Park", kind="park", distance_m=600, lat=18.52,
                 lng=73.85, indoor=False, needs_daylight=True)  # fmt: skip
MUSEUM = Candidate(id="way/3", name="City Museum", kind="museum", distance_m=900, lat=18.51,
                   lng=73.85, indoor=True, needs_daylight=False)  # fmt: skip
LIT_PARK = Candidate(id="way/9", name="Lit Park", kind="park", distance_m=400, lat=18.52,
                     lng=73.86, indoor=False, needs_daylight=False)  # fmt: skip
CANDIDATES = [PARK, MUSEUM, LIT_PARK]


def quest(**overrides: Any) -> dict[str, Any]:
    q = copy.deepcopy(BASE_QUEST)
    for key, value in overrides.items():
        if key == "photo_prompt":
            q["verification"]["photo_prompt"] = value
        elif key == "method":
            q["verification"]["method"] = value
        else:
            q[key] = value
    return q
