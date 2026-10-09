"""Sentry trace shape for /generate and /recap (MASTERSPEC §13), captured in-process.

The `gen_ai.*` attribute names are the convention Sentry's AI Agents view reads (D-62): if these
assertions fail after an SDK bump, check the convention before relaxing them.
"""

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from app.config import Settings
from app.observability import (
    ATTR_AGENT,
    ATTR_INPUT_TOKENS,
    ATTR_OPERATION,
    ATTR_OUTPUT_TOKENS,
    ATTR_PROVIDER,
    ATTR_REQUEST_MAX_TOKENS,
    ATTR_REQUEST_MODEL,
    ATTR_RESPONSE_MODEL,
    OP_CHAT,
    OP_INVOKE_AGENT,
    PROVIDER,
    SCRUBBED,
    sentry_options,
)
from app.services.llm_client import LLMClient
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

    def transaction(self, name: str) -> dict[str, Any]:
        [tx] = [e for e in self.events if e.get("transaction") == name]
        return tx

    def spans_with_op(self, op: str) -> list[dict[str, Any]]:
        """gen_ai spans of one op, flattened to {attribute: value} + the top-level fields."""
        out = []
        for s in self.gen_ai_spans:
            attrs = {k: v["value"] for k, v in s["attributes"].items()}
            if attrs.get("sentry.op") == op:
                out.append(
                    {**attrs, "name": s["name"], "status": s["status"], "trace_id": s["trace_id"]}
                )
        return out


@pytest.fixture
def captured() -> Iterator[Capture]:
    transport = Capture()
    settings = Settings(env="test", sentry_dsn="https://public@example.invalid/1")
    sentry_sdk.init(**sentry_options(settings), transport=transport)  # production options
    yield transport
    sentry_sdk.init()  # disable again for other tests


# --- /v1/quests/generate ------------------------------------------------------------------------


def test_generate_trace_has_named_transaction_spans_and_tags(captured: Capture) -> None:
    llm, _ = mock_llm(json.dumps({**LLM_QUEST, "place_id": "invented"}), json.dumps(LLM_QUEST))
    assert Harness(llm).generate().status_code == 200
    sentry_sdk.flush()
    tx = captured.transaction("quests.generate")
    ops = [s["op"] for s in tx["spans"]]
    for op in ("context.build", "scout.search", "memory.check", "validators"):
        assert op in ops, (op, ops)
    # gen_ai spans travel in a span-batch item but belong to the same transaction.
    [agent] = captured.spans_with_op(OP_INVOKE_AGENT)
    assert agent[ATTR_AGENT] == "quest_master"
    assert agent["name"] == "invoke_agent quest_master"
    chats = captured.spans_with_op(OP_CHAT)
    assert len(chats) == 2  # first try + one retry
    assert chats[0]["sentry.segment.name"] == "quests.generate"
    assert chats[0]["trace_id"] == tx["contexts"]["trace"]["trace_id"]
    assert [c["attempt"] for c in chats] == [0, 1]
    tags = tx["tags"]
    assert tags["source"] == "llm" and tags["retry"] == "1"
    assert tags["validator_failures"] == "V2"
    # No coordinates in the trace.
    assert "18.52" not in json.dumps(tx) + json.dumps(captured.gen_ai_spans)


def test_chat_spans_carry_the_required_gen_ai_attributes(captured: Capture) -> None:
    llm, _ = mock_llm(json.dumps(LLM_QUEST))
    assert Harness(llm).generate().status_code == 200
    sentry_sdk.flush()
    [chat] = captured.spans_with_op(OP_CHAT)
    assert chat["name"] == "chat quest"  # "chat {requested model}"
    assert chat[ATTR_OPERATION] == "chat"
    assert chat[ATTR_PROVIDER] == PROVIDER
    assert chat[ATTR_AGENT] == "quest_master"  # groups the call under its agent
    assert chat[ATTR_REQUEST_MODEL] == "quest"
    assert chat[ATTR_REQUEST_MAX_TOKENS] == 380
    assert chat[ATTR_RESPONSE_MODEL] == "tuned.gguf"  # what the server reported back
    assert chat[ATTR_INPUT_TOKENS] == 400
    assert chat[ATTR_OUTPUT_TOKENS] == 120
    assert "latency_ms" in chat
    # Prompts and completions are never attached: they carry interests and place names (§9.3).
    assert "gen_ai.input.messages" not in chat
    assert "gen_ai.output.messages" not in chat


def test_llm_failure_marks_the_chat_span_and_tags_the_fallback(captured: Capture) -> None:
    def refuse(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    llm = LLMClient("http://llm.test", transport=httpx.MockTransport(refuse))
    assert Harness(llm).generate().status_code == 200  # fallback still serves a quest
    sentry_sdk.flush()
    tx = captured.transaction("quests.generate")
    assert "fallback" in [s["op"] for s in tx["spans"]]
    assert tx["tags"]["source"] == "fallback"
    [chat] = captured.spans_with_op(OP_CHAT)
    assert chat["error.type"] in ("connection", "timeout", "http", "bad_response")
    assert chat["status"] == "error"  # the SDK maps internal_error → error on the wire


# --- /v1/recap/weekly ---------------------------------------------------------------------------


def test_recap_trace_is_named_spanned_and_tagged(captured: Capture) -> None:
    from tests.test_recap_api import Harness as RecapHarness
    from tests.test_recap_api import llm_recap
    from tests.test_recap_api import mock_llm as mock_recap_llm

    llm, _ = mock_recap_llm(llm_recap())
    assert RecapHarness(llm).recap().status_code == 200
    sentry_sdk.flush()
    tx = captured.transaction("recap.weekly")
    ops = [s["op"] for s in tx["spans"]]
    for op in ("context.build", "validators"):
        assert op in ops, (op, ops)
    [agent] = captured.spans_with_op(OP_INVOKE_AGENT)
    assert agent[ATTR_AGENT] == "chronicler"
    [chat] = captured.spans_with_op(OP_CHAT)
    assert chat[ATTR_OPERATION] == "chat"
    assert chat[ATTR_PROVIDER] == PROVIDER
    assert chat[ATTR_REQUEST_MAX_TOKENS] == 700  # RECAP_MAX_TOKENS, not the quest cap
    assert chat["sentry.segment.name"] == "recap.weekly"
    assert chat["trace_id"] == tx["contexts"]["trace"]["trace_id"]
    assert tx["tags"]["source"] == "llm" and tx["tags"]["retry"] == "0"
    assert tx["tags"]["validator_failures"] == "none"


def test_recap_without_llm_is_tagged_as_fallback(captured: Capture) -> None:
    from tests.test_recap_api import Harness as RecapHarness

    assert RecapHarness(None).recap().status_code == 200
    sentry_sdk.flush()
    tx = captured.transaction("recap.weekly")
    assert "fallback" in [s["op"] for s in tx["spans"]]
    assert tx["tags"]["source"] == "fallback"
    assert captured.spans_with_op(OP_CHAT) == []  # no model was called


def test_empty_week_is_still_tagged(captured: Capture) -> None:
    """A trace with no tags is a trace you can't filter, so even the no-op paths get tagged."""
    from tests.test_recap_api import Harness as RecapHarness

    assert RecapHarness(None, docs=[]).recap().status_code == 200
    sentry_sdk.flush()
    assert captured.transaction("recap.weekly")["tags"]["source"] == "empty"


# --- scrubbing on the streamed span path --------------------------------------------------------


def test_streamed_gen_ai_span_data_is_scrubbed_without_a_before_send_hook(
    captured: Capture,
) -> None:
    """A gen_ai span leaves in its own envelope item, so `span()` itself has to scrub (D-62).

    If this fails, `before_send_span` has started firing (or gen_ai spans stopped streaming) and
    the authoring-boundary scrub in `ScrubbedSpan` is no longer the only line of defence —
    check the SDK changelog before changing anything here.
    """
    from app.observability import chat_span

    with sentry_sdk.start_transaction(op="http.server", name="probe"):
        with chat_span("quest", agent="quest_master", max_tokens=380, attempt=0) as s:
            s.set_data("interests", "coffee near my flat")
            s.set_data("echo", "meet at 18.5204,73.8567")
    sentry_sdk.flush()

    [chat] = captured.spans_with_op(OP_CHAT)
    assert chat["interests"] == SCRUBBED
    assert "18.5204" not in chat["echo"]
    assert "18.5204" not in json.dumps(captured.gen_ai_spans)
