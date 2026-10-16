# Architecture

## Why three agents

One agent trying to do everything gets confused and untestable. Splitting by
responsibility gives us:

- **Sourcing agent** — *find people.* Pure data work: providers, dedupe,
  scoring. Never touches a phone.
- **Manager agent** — *decide.* Owns prioritization, compliance gates,
  dispatch, and the learning loop. The only agent allowed to decide *who*
  gets called *when* with *which script*.
- **Voice agents (pool)** — *talk.* Stateless per-call Pipecat pipelines.
  They know the lead, the script variant, and the tools. They report outcomes;
  they never decide strategy.

## Inter-agent communication

Everything flows through `EventBus` (`agents/bus.py`) as typed `Event`s
(`agents/models.py`). The catalog:

| Event | From → To | Payload |
|---|---|---|
| `lead.discovered` | sourcing → manager | `lead` |
| `lead.scored` | manager → bus | `lead_id`, `score` |
| `call.requested` | manager → voice pool | `lead`, `variant` |
| `call.started` | voice → bus | `call_id`, `lead_id`, `variant_id` |
| `call.ended` | voice → manager | `call` (CallRecord) |
| `interview.booked` | voice → manager | `lead_id`, `when`, `notes` (+ human notify) |
| `dnc.added` | voice → bus | `phone`, `reason` |
| `variant.promoted` | learning → bus | `variant_id`, `stats` |
| `learning.report` | learning → manager | `report` text |

v1 the bus is in-process asyncio. The interface is deliberately tiny
(`publish`/`subscribe`) so v2 can swap in Redis pub/sub and run voice
workers on separate machines with zero agent-code changes.

Shared state lives in `Store` (SQLite now, Postgres later): leads, calls,
script variants, DNC list. Agents never share memory directly.

## The learning loop

Each call is tagged with its script variant. Outcomes map to rewards:
interview 1.0, callback 0.5, conversation 0.25, voicemail 0.05, else 0.

- **Stats**: per-variant reward with Laplace smoothing —
  `(reward + 1) / (calls + 4)` — so a variant with 1 lucky call doesn't beat
  one with 30 solid calls.
- **Selection**: epsilon-greedy (default ε=0.15). 85% exploit the leader,
  15% explore, so the system never freezes on an early winner.
- **Promotion**: a variant is crowned (`variant.promoted`) after ≥10 calls
  with a clear lead.
- **New variants**: `propose_variant()` drafts experimental tweaks off the
  winner. They start `active=False` — a human (or the manager with an LLM
  judge) approves before they enter rotation.

`scripts/seed_demo.py` proves this offline: with true interview rates of
4%/12%/7%, the loop discovers the 12% variant and concentrates calls on it.

## Compliance (conservative US defaults)

- Mandatory AI disclosure as the first spoken line; `assert_disclosure_present`
  fails the pipeline build if it's ever missing.
- Calling window: 9am–8pm *recipient-local* (zoneinfo), weekdays only.
- DNC list hard-blocks dispatch; a mid-call DNC request ends the call.
- Max 4 attempts per lead, then `exhausted`.
- Twilio `machine_detection` enabled so we don't pitch voicemail as if live.

## Voice pipeline (Pipecat 1.12, verified)

```
Twilio Media Stream (FastAPIWebsocketTransport + TwilioFrameSerializer)
  → DeepgramSTTService → LLMContextAggregatorPair.user()
  → OpenAILLMService (gpt-4o-mini, FunctionSchema tools)
  → CartesiaTTSService → transport.output()
```

The bot speaks first via `TTSSpeakFrame(disclosure + opener)` on
`on_client_connected`. Tools: `end_call_with_outcome`, `book_interview`,
`request_callback`, `add_to_dnc`. Every tool result funnels into
`VoiceSession.finalize()` → `call.ended` → manager → learning.

## Cost estimate (per minute of talk time)

| Stack | ~$/min |
|---|---|
| Self-hosted (this repo): Twilio ~$0.014 + Deepgram ~$0.01 + GPT-4o-mini ~$0.01 + Cartesia ~$0.02 | **~$0.05** |
| Hosted (Vapi/Retell/Bland) | $0.07–$0.31 |

100 calls × 3 min ≈ **$15** self-hosted.

## Production roadmap

1. Redis bus + Postgres store (multi-machine voice workers).
2. Calendar integration for `book_interview` (Google Calendar).
3. Real sourcing providers (Apollo/RocketReach API, SerpAPI discovery).
4. LLM judge on transcripts: auto-tag objection types, draft new variants.
5. Dashboard UI on `/api/*`.
6. Legal review of calling compliance for target jurisdictions.
