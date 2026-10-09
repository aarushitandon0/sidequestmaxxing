# Reading a Sidequestmaxxing trace

Two things live here:

1. **A map of what a trace contains** — reference, true today, checked by tests.
2. **A README section template** ("How I debugged with traces") with `TODO` placeholders.
   Fill it in from a real trace, then paste it into the README at P22. **Don't invent the story**
   — an empty placeholder is better than a plausible-sounding bug that never happened
   (CLAUDE.md: be honest in docs and numbers).

## What a traced request looks like

Two endpoints are traced end to end: `POST /v1/quests/generate` (transaction `quests.generate`)
and `POST /v1/recap/weekly` (transaction `recap.weekly`).

```
quests.generate                       ← transaction; tags: source, retry, validator_failures
├── context.build                     data: weather_source, indoor_only
├── memory.check                      data: memories (count), error (type name only)
├── scout.search                      data: found, candidates, dropped
├── gen_ai.invoke_agent               name "invoke_agent quest_master"   ┐ streamed as their own
│   ├── gen_ai.chat  (attempt 0)      name "chat {model}"                │ envelope item, same
│   └── gen_ai.chat  (attempt 1)      only when a validator rejected #0  ┘ trace_id
├── validators                        data: ok, failures (e.g. ["V2"])
└── fallback                          only when the LLM path gave up; data: reason
```

`recap.weekly` is the same shape with `context.build` (named `recap.gather`) and the
`chronicler` agent, and no scout/memory steps.

### The three tags to filter on

| Tag | Values | What it answers |
|---|---|---|
| `source` | `llm`, `fallback`, `empty`, and `cached:llm` / `cached:fallback` on a repeat recap | Did the model actually serve this, the fallback engine, or the stored recap? |
| `retry` | `0`, `1` | Did the first draft fail validation? |
| `validator_failures` | `none`, or `V2`, `V5,V9`, … | Which rule rejected a draft. |

A quest served by the fallback engine is **not** an error — `/v1/quests/generate` is required to
succeed with the LLM down (MASTERSPEC §2.4). `source:fallback` is the signal that it happened.

### On the model spans

`gen_ai.chat` carries the model, `max_tokens`, attempt number, token counts and `latency_ms`.
It deliberately does **not** carry the prompt or the completion: those hold the player's
interests and nearby place names (§9.3). So a trace tells you *that* a draft failed `V2` and how
long it took, never *what* the model wrote. To see a bad generation, reproduce it locally.

Coordinates and device ids cannot appear anywhere in a trace: `span()` scrubs span data as it is
authored and `before_send` scrubs the rest (D-62). Tests assert both paths.

## README section template — "How I debugged with traces"

> Copy from here down into the README, replace every `TODO`, and delete any bullet that didn't
> happen. Keep the real span names and tag values so a reader can follow along in their own trace.

---

### How I debugged with traces

Every quest generation is one Sentry trace: context building, the memory check, the place
search, the model call(s), validation, and the fallback if it fired. Three tags —
`source`, `retry`, `validator_failures` — make the interesting requests findable.

**The bug:** TODO — one sentence, in player-visible terms ("some quests came back generic even
though there were good places nearby").

**What the trace showed:** TODO — the span that stood out and the number that gave it away.
For example: `scout.search` showed `candidates: TODO` where `found: TODO`, so the places existed
and were being dropped after the search, not missing from the database.

**What I'd have done without it:** TODO — the thing you would have guessed at first, and why it
would have been the wrong place to look.

**The fix:** TODO — what changed, with the file. TODO — what the same trace looks like now.

Honest limits, for anyone reading a trace of their own:

- Prompts and completions are **not** in the trace, on purpose (§9.3) — a trace tells you a draft
  failed `V2`, never what the model wrote. Reproducing a bad generation means running it locally.
- `source:fallback` means the fallback engine served the quest. That's the system working as
  designed with the model down, not an error to chase.
- Frontend traces are sampled at 10%, so the browser half of a specific request is often missing.
