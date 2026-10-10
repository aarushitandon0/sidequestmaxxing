"""Table-driven tests for V1-V13 (MASTERSPEC §7.4) and the §9.2 banned-term lint."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.models.quest import QuestDraft
from app.services.places_repo import Candidate
from app.validators import ValidationContext, banned_hits, contact_hits, people_hits, validate_quest
from app.validators.core import quest_memory_text, v13_event_window
from tests.quest_factory import BASE_QUEST, CANDIDATES, quest

CTX = ValidationContext(minutes_available=60, indoor_only=False, daylight_minutes_left=240)


def ids(q: Any, ctx: ValidationContext = CTX, **kw: Any) -> list[str]:
    return validate_quest(q, ctx, CANDIDATES, **kw).failure_ids


def test_base_quest_is_valid() -> None:
    result = validate_quest(BASE_QUEST, CTX, CANDIDATES)
    assert result.ok, result.failures
    assert isinstance(result.quest, QuestDraft)


def test_accepts_json_string_and_model() -> None:
    assert ids(json.dumps(BASE_QUEST)) == []
    assert ids(QuestDraft.model_validate(BASE_QUEST)) == []


# --- V1 parse + schema --------------------------------------------------------------------------

V1_BAD = [
    "not json",
    '{"title": "x"',
    "[1, 2, 3]",
    "null",
    json.dumps(quest(category="pirate")),
    json.dumps(quest(est_minutes="thirty")),
    json.dumps(quest(xp=999)),  # LLM must not set server-owned fields
    json.dumps(quest(rarity="legendary")),
    json.dumps({k: v for k, v in BASE_QUEST.items() if k != "safety_note"}),
    json.dumps(quest(method="photo", photo_prompt=None)),
    json.dumps(quest(place_id=None, method="checkin", photo_prompt=None)),
    json.dumps(quest(briefing="too short")),
    json.dumps(quest(est_minutes=500)),
]


@pytest.mark.parametrize("raw", V1_BAD)
def test_v1_rejects(raw: str) -> None:
    result = validate_quest(raw, CTX, CANDIDATES)
    assert result.quest is None
    assert result.failure_ids == ["V1"]


V1_GOOD = [
    quest(),
    quest(place_id=None, method="honor", photo_prompt=None),
    quest(place_id=None),  # photo + no place is fine
    quest(method="checkin", photo_prompt=None),
    quest(est_minutes=5),
    quest(title="  Padded Title  "),  # whitespace stripped
]


@pytest.mark.parametrize("q", V1_GOOD)
def test_v1_accepts(q: dict[str, Any]) -> None:
    assert "V1" not in ids(q)


def test_v1_tolerates_llm_wrapper_text_only_if_caller_extracts() -> None:
    # Raw decoding may wrap JSON in prose; V1 is strict by design (extraction is the client's job).
    assert ids("Here you go: " + json.dumps(BASE_QUEST)) == ["V1"]


# --- V2 grounding -------------------------------------------------------------------------------


@pytest.mark.parametrize("pid", ["way/2", "way/3", "way/9", None, "way/2", None])
def test_v2_accepts(pid: str | None) -> None:
    kw: dict[str, Any] = {"place_id": pid}
    if pid is None:
        kw.update(method="photo")
    assert "V2" not in ids(quest(**kw))


@pytest.mark.parametrize("pid", ["node/999", "way/22", "WAY/2", "", "Banyan Park", "way/2 "])
def test_v2_rejects_invented_places(pid: str) -> None:
    q = quest(place_id=pid)
    out = ids(q)
    # "way/2 " is stripped by the schema → valid; everything else must fail grounding.
    if pid.strip() == "way/2":
        assert "V2" not in out
    else:
        assert "V2" in out


def test_v2_with_no_candidates() -> None:
    assert "V2" in validate_quest(quest(), CTX, []).failure_ids
    assert "V2" not in validate_quest(quest(place_id=None), CTX, []).failure_ids


# --- V3 minutes ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("est", "avail"), [(5, 10), (10, 10), (30, 60), (60, 60), (45, 180), (180, 180)]
)
def test_v3_accepts(est: int, avail: int) -> None:
    ctx = ValidationContext(avail, daylight_minutes_left=999)
    assert "V3" not in ids(quest(est_minutes=est), ctx)


@pytest.mark.parametrize(
    ("est", "avail"), [(11, 10), (61, 60), (90, 45), (180, 179), (31, 30), (12, 10)]
)
def test_v3_rejects(est: int, avail: int) -> None:
    ctx = ValidationContext(avail, daylight_minutes_left=999)
    assert "V3" in ids(quest(est_minutes=est), ctx)


# --- V4 banned terms (§9.2) ---------------------------------------------------------------------

V4_SAFE = [
    "Climb the stairs at the museum and find the top gallery.",
    "Climbing the stairs to the library reading room counts.",
    "Visit a diverse garden full of flowers.",
    "Walk past the driveway and turn left at the bakery.",
    "Walk to the main gate and look for the old sign.",
    "Take a shot of the view from the bench.",
    "Find a bird feeder and watch from a distance.",
    "Use pedestrian crossings and stay aware of traffic.",
    "Notice the edges of leaves.",
    "Spot the ducks from the path.",
    # Benign phrasings the P20 rule families could plausibly over-match (D-64). A quest that
    # trips one of these is a false positive: the lint is strict, but it must not reject an
    # ordinary walk. Two of these did trip during P20 and the rules were narrowed.
    "Pick out three different flowers in the garden and name their colours.",
    "Wait at the bus stop by the park entrance and watch the sky change colour.",
    "Count the benches along the main path and note the oldest one.",
    "Climb the stairs at the library to the reading room on the top floor.",
    "Watch the fountain until the jets change pattern, then head home.",
    "Follow the river path east until you reach the second bridge.",
    "If you hear thunder, turn back and finish this another day.",
    "Note down what the plaque on the monument says.",
    "Find the gate of the old fort and read the inscription above it.",
    "Count how many arches the aqueduct has from the viewpoint.",
    "Give yourself twenty minutes to wander the market without buying anything.",
    "Photograph the pattern of leaves on the ground under the big tree.",
    "Stay on the lit main road and come back before dark.",
]


@pytest.mark.parametrize("text", V4_SAFE)
def test_v4_allows(text: str) -> None:
    assert [h.rule for h in banned_hits(text)] == []


# Known false positives we accept on purpose: the lint is strict, and the fallback engine and
# training data simply avoid these phrasings. Do not "fix" these by loosening rules.
V4_STRICT = [
    ("Dive deep into your thoughts.", "dive"),
    ("Look at the swimming ducks from the path.", "swim"),
    ("Order a mushroom-free snack.", "mushroom_food"),
    ("Do not climb anything.", "climb"),
    ("Find a remote corner of the library.", "isolated"),
    ("No drones allowed here.", "drone"),
]


@pytest.mark.parametrize(("text", "rule"), V4_STRICT)
def test_v4_is_strict_even_when_harmless(text: str, rule: str) -> None:
    assert [h.rule for h in banned_hits(text)] == [rule]


V4_UNSAFE = [
    ("Climb the rock face behind the temple.", "climb"),
    ("Swim across the lake.", "swim"),
    ("Dive off the jetty.", "dive"),
    ("Stand at the edge of the cliff.", "cliff"),
    ("Walk to the edge of the reservoir.", "edge_of"),
    ("Trespass into the old factory.", "trespass"),
    ("Explore the private property behind the wall.", "private_property"),
    ("Jump the gate at the back.", "gate_jump"),
    ("Hop over the fence to get a better view.", "fence_jump"),
    ("Cross the highway to reach the hill.", "cross_road"),
    ("Cross the road without the signal.", "cross_road"),
    ("Drive to the lake.", "drive"),
    ("Get a little drunk at the market.", "alcohol"),
    ("Grab a beer at sunset.", "alcohol"),
    ("Forage for berries.", "forage"),
    ("Eat the wild berries you find.", "eat_wild"),
    ("Pick and taste a mushroom.", "mushroom_food"),
    ("Feed the ducks some bread.", "feed_animals"),
    ("Pet the stray dogs.", "touch_animals"),
    ("Approach a stranger and ask their name.", "strangers"),
    ("Follow someone through the market.", "follow_someone"),
    ("Talk to the kids at the playground.", "children"),
    ("Walk the trail at night alone.", "night_alone"),
    ("Meet at midnight by the fountain.", "midnight"),
    ("Find an isolated spot.", "isolated"),
    ("Light fireworks in the park.", "fireworks"),
    ("Fly a drone over the park.", "drone"),
    ("Explore the abandoned mill.", "abandoned"),
    ("Sit on the rooftop.", "ledge"),
    ("Wade into the stream.", "wade"),
    ("Start a bonfire.", "fire"),
    ("Bring a knife.", "weapons"),
    # Evasion attempts
    ("Swim​ in the pond.", "swim"),  # zero-width space
    ("Сlimb the wall.", "climb"),  # Cyrillic С
    ("CLIMB THE TOWER", "climb"),
    ("clímb the hill", "climb"),  # accent
    ("ｓｗｉｍ", "swim"),  # fullwidth
]


@pytest.mark.parametrize(("text", "rule"), V4_UNSAFE)
def test_v4_rejects(text: str, rule: str) -> None:
    assert rule in [h.rule for h in banned_hits(text)]


@pytest.mark.parametrize(
    "field", ["title", "briefing", "objective", "safety_note", "off_screen_tip", "photo_prompt"]
)
def test_v4_checks_every_string_field(field: str) -> None:
    bad = {
        "title": "Swim Quest Deluxe",
        "briefing": "Go to the park and swim in the pond, it will be fun and refreshing for you.",
        "objective": "Swim one lap.",
        "safety_note": "Do not swim after eating.",  # strict: even negated mentions fail
        "off_screen_tip": "Swim without the phone.",
        "photo_prompt": "the swimming pond",
    }[field]
    assert "V4" in ids(quest(**{field: bad}))


# --- V5 safety note -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "note",
    [
        "Stay on paths.",
        "x" * 10,
        "x" * 140,
        "Tell someone where you go.",
        "Keep to busy public areas.",
        "Head home before dark, please.",
    ],
)
def test_v5_accepts(note: str) -> None:
    assert "V5" not in ids(quest(safety_note=note))


@pytest.mark.parametrize("note", ["Be safe", "ok", "x" * 9, "   tiny   ", "Careful!", "."])
def test_v5_rejects_short(note: str) -> None:
    assert "V5" in ids(quest(safety_note=note))


def test_v5_too_long_is_caught_by_schema() -> None:
    assert ids(quest(safety_note="x" * 141)) == ["V1"]


# --- V6 photo prompts never about people --------------------------------------------------------

V6_OK = [
    "banyan tree aerial roots",
    "a carved stone plaque",
    "three different leaves side by side",
    "your snack on a plate",
    "the view from the hilltop bench",
    "an interesting door",
    "the shadow of a lamp post",
    "here is the fountain",  # 'here' ≠ 'her'
]

V6_BAD = [
    "a selfie at the gate",
    "people at the market",
    "the vendor at the stall",
    "kids playing cricket",
    "a stranger's dog",
    "your friend smiling",
    "faces in the crowd",
    "a woman selling flowers",
    "yourself next to the statue",
    "the barista making coffee",
    "Someone reading on a bench",
    "a portrait of a local",
]


@pytest.mark.parametrize("prompt", V6_OK)
def test_v6_accepts(prompt: str) -> None:
    assert people_hits(prompt) == []
    assert "V6" not in ids(quest(photo_prompt=prompt))


@pytest.mark.parametrize("prompt", V6_BAD)
def test_v6_rejects(prompt: str) -> None:
    assert people_hits(prompt)
    assert "V6" in ids(quest(photo_prompt=prompt))


def test_v6_ignores_non_photo_quests() -> None:
    assert "V6" not in ids(quest(method="checkin", photo_prompt=None))


# --- V7 lengths, word count, spoken style -------------------------------------------------------


@pytest.mark.parametrize(
    "kw",
    [
        {},
        {"title": "Abc"},
        {"title": "x" * 60},
        {"briefing": " ".join(["word"] * 70)},
        {"objective": "x" * 140},
        {"off_screen_tip": "x" * 100},
    ],
)
def test_v7_accepts(kw: dict[str, Any]) -> None:
    assert "V7" not in ids(quest(**kw))


@pytest.mark.parametrize(
    "kw",
    [
        {"briefing": " ".join(["go"] * 71)},
        {"briefing": " ".join(["a"] * 100)},
        {"briefing": "Walk to the park and find the oldest tree you can spot today 🌳 okay?"},
        {"title": "Tree Time 🌳"},
        {"objective": "Find a tree #touchgrass"},
        {"off_screen_tip": "Pocket it ✨"},
    ],
)
def test_v7_rejects(kw: dict[str, Any]) -> None:
    assert "V7" in ids(quest(**kw))


def test_v7_rechecks_lengths_on_model_construct() -> None:
    # An object built without validation (model_construct) still gets length checks.
    q = QuestDraft.model_construct(
        **{**QuestDraft.model_validate(BASE_QUEST).__dict__, "title": "x" * 80}
    )
    from app.validators.core import v7_lengths

    assert [f.id for f in v7_lengths(q)] == ["V7"]


# --- V8 contact info ----------------------------------------------------------------------------

V8_OK = [
    "Walk 2 km to the park.",
    "Spend 10-15 minutes there.",
    "Find the 1901 memorial.",
    "Look for gate no. 3 near bus stop 114.",
    "Walk for 45 minutes.",
    "Count to 100 slowly.",
]

V8_BAD = [
    "Visit https://example.com for the map.",
    "Check www.parks.gov first.",
    "Email ranger@parks.org.",
    "Call +91 98765 43210 when you arrive.",
    "Call (020) 2553-1234.",
    "Info at parksdept.in",
]


@pytest.mark.parametrize("text", V8_OK)
def test_v8_accepts(text: str) -> None:
    assert contact_hits(text) == []
    assert "V8" not in ids(quest(objective=text))


@pytest.mark.parametrize("text", V8_BAD)
def test_v8_rejects(text: str) -> None:
    assert contact_hits(text)
    assert "V8" in ids(quest(objective=text))


# --- V9 indoor_only -----------------------------------------------------------------------------

INDOOR = ValidationContext(60, indoor_only=True, daylight_minutes_left=240)


@pytest.mark.parametrize(
    "kw",
    [
        {"place_id": "way/3", "method": "checkin", "photo_prompt": None},
        {"place_id": None},
        {"place_id": None, "method": "honor", "photo_prompt": None},
        {"place_id": "way/3", "photo_prompt": "a museum ticket stub"},
        {"place_id": "way/3", "method": "honor", "photo_prompt": None},
        {"place_id": None, "photo_prompt": "your sketch"},
    ],
)
def test_v9_accepts(kw: dict[str, Any]) -> None:
    assert "V9" not in ids(quest(**kw), INDOOR)


@pytest.mark.parametrize(
    "kw",
    [
        {"place_id": "way/2"},
        {"place_id": "way/9"},
        {"place_id": "way/2", "method": "checkin", "photo_prompt": None},
        {"place_id": "way/9", "method": "honor", "photo_prompt": None},
        {"place_id": "node/unknown"},  # unknown place can't be proven indoor
        {"place_id": "way/2", "est_minutes": 5},
    ],
)
def test_v9_rejects(kw: dict[str, Any]) -> None:
    assert "V9" in ids(quest(**kw), INDOOR)


def test_v9_noop_when_not_indoor_only() -> None:
    assert "V9" not in ids(quest(place_id="way/2"))


# --- V10 daylight -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("place", "est", "daylight"),
    [
        ("way/2", 30, 60),  # exactly est + 30
        ("way/2", 30, 240),
        ("way/3", 30, 0),  # museum doesn't need daylight
        ("way/9", 30, 0),  # lit park
        (None, 30, 0),  # place-less
        ("way/3", 60, None),
    ],
)
def test_v10_accepts(place: str | None, est: int, daylight: int | None) -> None:
    ctx = ValidationContext(180, daylight_minutes_left=daylight)
    kw: dict[str, Any] = {"place_id": place, "est_minutes": est}
    assert "V10" not in ids(quest(**kw), ctx)


@pytest.mark.parametrize(
    ("est", "daylight"), [(30, 59), (30, 0), (5, 34), (60, 60), (120, 100), (30, None)]
)
def test_v10_rejects_at_dusk(est: int, daylight: int | None) -> None:
    ctx = ValidationContext(180, daylight_minutes_left=daylight)
    assert "V10" in ids(quest(place_id="way/2", est_minutes=est), ctx)


# --- V11 category -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cat", ["explorer", "naturalist", "social", "foodie", "creative", "fitness", "mindful"]
)
def test_v11_accepts(cat: str) -> None:
    assert "V11" not in ids(quest(category=cat))


@pytest.mark.parametrize("cat", ["pirate", "Explorer", "", "fighter", "party", "drinking"])
def test_v11_rejects(cat: str) -> None:
    # Schema catches it first (V1); a model_construct bypass is caught by V11 itself.
    assert ids(quest(category=cat)) == ["V1"]
    from app.validators.core import v11_category

    q = QuestDraft.model_construct(
        **{**QuestDraft.model_validate(BASE_QUEST).__dict__, "category": cat}
    )
    assert [f.id for f in v11_category(q)] == ["V11"]


# --- V12 near-duplicates ------------------------------------------------------------------------


def _unit(i: int, n: int = 8) -> list[float]:
    return [1.0 if j == i else 0.0 for j in range(n)]


@pytest.mark.parametrize(
    "recent",
    [
        [],
        [_unit(1)],
        [_unit(1), _unit(2)],
        [[1.0, 1.0] + [0.0] * 6],
        [[-1.0] + [0.0] * 7],
        [[0.89, 0.456] + [0.0] * 6],
    ],
)
def test_v12_accepts(recent: list[list[float]]) -> None:
    assert "V12" not in ids(quest(), quest_embedding=_unit(0), recent_embeddings=recent)


@pytest.mark.parametrize(
    "recent",
    [
        [_unit(0)],
        [_unit(1), _unit(0)],
        [[2.0] + [0.0] * 7],
        [[0.95, 0.05] + [0.0] * 6],
        [[1.0, 0.1] + [0.0] * 6],
        [[0.9, 0.3] + [0.0] * 6],
    ],
)
def test_v12_rejects(recent: list[list[float]]) -> None:
    assert "V12" in ids(quest(), quest_embedding=_unit(0), recent_embeddings=recent)


def test_v12_skipped_without_embedding() -> None:
    assert "V12" not in ids(quest(), recent_embeddings=[_unit(0)])


def test_collects_multiple_failures() -> None:
    bad = quest(place_id="node/x", est_minutes=90, objective="Swim to https://x.com")
    assert set(ids(bad)) >= {"V2", "V3", "V4", "V8"}


def test_quest_memory_text() -> None:
    q = QuestDraft.model_validate(BASE_QUEST)
    assert quest_memory_text(q, "Banyan Park").endswith("naturalist — Banyan Park")


# --- V13: event time window (P23) ------------------------------------------------------------

EVENT_NOW = datetime(2026, 10, 11, 2, 0, tzinfo=UTC)


def _event_ctx() -> ValidationContext:
    return ValidationContext(minutes_available=60, daylight_minutes_left=300, now=EVENT_NOW)


def event_candidate(*, starts: datetime, ends: datetime, cid: str = "serp/walk") -> Candidate:
    return Candidate(
        id=cid,
        name="Heritage Walk",
        kind="heritage",
        distance_m=600,
        lat=18.52,
        lng=73.85,
        indoor=False,
        needs_daylight=True,
        event_window=(starts, ends),
    )


def _v13(q: dict[str, Any], candidates: list[Candidate]) -> list[str]:
    draft = QuestDraft.model_validate(q)
    return [f.id for f in v13_event_window(draft, _event_ctx(), candidates, EVENT_NOW)]


def test_v13_accepts_event_already_running() -> None:
    """A walk that began 30 minutes ago and runs another 90 is joinable, not expired."""
    cand = event_candidate(
        starts=EVENT_NOW - timedelta(minutes=30), ends=EVENT_NOW + timedelta(minutes=90)
    )
    assert _v13(quest(place_id=cand.id, est_minutes=45), [cand]) == []


def test_v13_rejects_event_that_already_ended() -> None:
    cand = event_candidate(
        starts=EVENT_NOW - timedelta(hours=3), ends=EVENT_NOW - timedelta(hours=1)
    )
    assert _v13(quest(place_id=cand.id), [cand]) == ["V13"]


def test_v13_rejects_event_starting_after_the_window() -> None:
    cand = event_candidate(
        starts=EVENT_NOW + timedelta(hours=5), ends=EVENT_NOW + timedelta(hours=7)
    )
    assert _v13(quest(place_id=cand.id, est_minutes=30), [cand]) == ["V13"]


def test_v13_accepts_event_starting_just_inside_the_window() -> None:
    cand = event_candidate(
        starts=EVENT_NOW + timedelta(minutes=40), ends=EVENT_NOW + timedelta(hours=2)
    )
    assert _v13(quest(place_id=cand.id, est_minutes=45), [cand]) == []


def test_v13_boundary_start_exactly_at_now_plus_est_minutes_passes() -> None:
    cand = event_candidate(
        starts=EVENT_NOW + timedelta(minutes=45), ends=EVENT_NOW + timedelta(hours=2)
    )
    assert _v13(quest(place_id=cand.id, est_minutes=45), [cand]) == []


def test_v13_boundary_end_exactly_at_now_passes() -> None:
    cand = event_candidate(starts=EVENT_NOW - timedelta(hours=2), ends=EVENT_NOW)
    assert _v13(quest(place_id=cand.id, est_minutes=45), [cand]) == []


def test_v13_ignores_place_candidates() -> None:
    assert _v13(quest(place_id="way/2"), list(CANDIDATES)) == []


def test_v13_ignores_placeless_quests() -> None:
    assert _v13(quest(place_id=None), []) == []


def test_v13_ignores_a_place_id_that_matches_no_candidate() -> None:
    assert _v13(quest(place_id="serp/missing"), []) == []


def test_validate_quest_without_now_skips_v13() -> None:
    """Every pre-P23 caller passes no `now`, so V13 must be a no-op for them."""
    ctx = ValidationContext(minutes_available=60, daylight_minutes_left=300)
    cand = event_candidate(
        starts=EVENT_NOW - timedelta(hours=3), ends=EVENT_NOW - timedelta(hours=1)
    )
    assert "V13" not in validate_quest(quest(place_id=cand.id), ctx, [cand]).failure_ids


def test_validate_quest_with_now_runs_v13() -> None:
    cand = event_candidate(
        starts=EVENT_NOW - timedelta(hours=3), ends=EVENT_NOW - timedelta(hours=1)
    )
    result = validate_quest(quest(place_id=cand.id), _event_ctx(), [cand])
    assert "V13" in result.failure_ids
