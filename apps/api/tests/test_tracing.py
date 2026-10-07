"""Sentry trace shape for /v1/quests/generate (MASTERSPEC §13), captured in-process."""

import json
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.config import Settings
from app.observability import sentry_options
from tests.test_quests_api import LLM_QUEST, Harness, mock_llm


class Capture(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []
        self.gen_ai_spans: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            if item.type == "transaction":
                self.events.append(item.payload.json)
            elif item.payload.json and "items" in item.payload.json:
                # This SDK ships gen_ai.* spans as a separate span-batch item for AI monitoring.
                self.gen_ai_spans.extend(item.payload.json["items"])


@pytest.fixture
def captured() -> Iterator[Capture]:
    transport = Capture()
    settings = Settings(env="test", sentry_dsn="https://public@example.invalid/1")
    sentry_sdk.init(**sentry_options(settings), transport=transport)  # production options
    yield transport
    sentry_sdk.init()  # disable again for other tests


def test_generate_trace_has_named_transaction_spans_and_tags(captured: Capture) -> None:
    llm, _ = mock_llm(json.dumps({**LLM_QUEST, "place_id": "invented"}), json.dumps(LLM_QUEST))
    assert Harness(llm).generate().status_code == 200
    sentry_sdk.flush()
    [tx] = [e for e in captured.events if e.get("transaction") == "quests.generate"]
    ops = [s["op"] for s in tx["spans"]]
    for op in ("context.build", "scout.search", "memory.check", "validators"):
        assert op in ops, (op, ops)
    # gen_ai.chat spans travel in a span-batch item but belong to the same transaction.
    llm_spans = captured.gen_ai_spans
    assert len(llm_spans) == 2  # first try + one retry
    attrs = llm_spans[0]["attributes"]
    assert attrs["sentry.op"]["value"] == "gen_ai.chat"
    assert attrs["sentry.segment.name"]["value"] == "quests.generate"
    assert attrs["gen_ai.usage.output_tokens"]["value"] == 120
    assert llm_spans[0]["trace_id"] == tx["contexts"]["trace"]["trace_id"]
    tags = tx["tags"]
    assert tags["source"] == "llm" and tags["retry"] == "1"
    assert tags["validator_failures"] == "V2"
    # No coordinates in the trace.
    assert "18.52" not in json.dumps(tx) + json.dumps(llm_spans)
