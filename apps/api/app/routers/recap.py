"""POST /v1/recap/weekly — the Weekly Chronicle (MASTERSPEC §3.3, §7.7).

Gathers the last 7 local days of completions → Chronicler (same LLM endpoint) → R1-R7 →
facts-only template on failure → stored in `recaps`, one per (device, week_start).
Works with the LLM service down. Stats are always computed by the server.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import PyMongoError

from app.agents.chronicler import RecapInput, run_chronicler
from app.deps import DeviceId, Now, get_db, get_llm_client
from app.errors import db_unavailable
from app.models.recap import WeeklyRecap
from app.observability import name_transaction, span, tag_outcome
from app.ratelimit import RECAP_LIMIT, limiter
from app.services.completion import local_date
from app.services.db import Doc
from app.services.llm_client import LLMClient
from app.services.recaps import (
    completion_ids,
    device_persona,
    find_recap,
    save_recap,
    stored_at,
    to_recap_completion,
    week_completions,
    week_label,
    window,
)
from app.validators.recap import RecapStats

router = APIRouter(prefix="/v1/recap", tags=["recap"])
Db = Annotated[AsyncDatabase[Doc], Depends(get_db)]

EMPTY_TEXT = (
    "No quests in your chronicle yet this week. The map is waiting: take one short side quest"
    " and this page will tell the story of your week."
)


def _out(doc: Doc) -> WeeklyRecap:
    return WeeklyRecap(
        id=str(doc["_id"]),
        week_start=doc["week_start"],
        week_end=doc["week_end"],
        text=doc["text"],
        stats=RecapStats.model_validate(doc["stats"]),
        source=doc["source"],
        created_at=stored_at(doc),
    )


@router.post("/weekly", response_model=WeeklyRecap)
@limiter.limit(RECAP_LIMIT)
async def weekly_recap(
    request: Request,
    device_id: DeviceId,
    db: Db,
    llm: Annotated[LLMClient | None, Depends(get_llm_client)],
    now: Now,
) -> WeeklyRecap:
    name_transaction("recap.weekly")
    try:
        persona, offset = await device_persona(db, device_id)
        start, end = window(local_date(now, offset))
        with span("context.build", name="recap.gather") as s:
            docs = await week_completions(db, device_id, start)
            s.set_data("completions", len(docs))
        if not docs:
            tag_outcome("empty", 0)
            return WeeklyRecap(id=None, week_start=start, week_end=end, text=EMPTY_TEXT,
                               stats=RecapStats(quests=0, minutes=0, top_category=None),
                               source="empty", created_at=None)  # fmt: skip
        ids = completion_ids(docs)
        stored = await find_recap(db, device_id, start)
        if stored is not None and stored.get("completion_ids") == ids:
            # Idempotent: same week, same completions → same recap, no LLM call.
            tag_outcome(f"cached:{stored['source']}", stored.get("retries", 0))
            return _out(stored)
    except PyMongoError as exc:
        raise db_unavailable() from exc

    inp = RecapInput(persona=persona, week=week_label(start, end),
                     completions=[to_recap_completion(d) for d in docs])  # fmt: skip
    result = await run_chronicler(inp, llm)
    tag_outcome(result.source, result.retries, result.validator_failures)
    doc: Doc = {
        "_id": str(uuid.uuid4()),
        "device_id": device_id,
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "text": result.recap.text,
        "stats": result.recap.stats.model_dump(),
        "source": result.source,
        "model": result.model,
        "retries": result.retries,
        "validator_failures": result.validator_failures,
        "fallback_reason": result.fallback_reason,
        "completion_ids": ids,
        "created_at": now,
    }
    try:
        await save_recap(db, doc)
    except PyMongoError as exc:
        raise db_unavailable() from exc
    return _out(doc)
