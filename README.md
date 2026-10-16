# Mercury Mesh

*Autonomous agents that turn cold calls into interviews.*

Mercury Mesh finds hiring managers, recruiters, and vendors, calls them,
pitches a candidate, and books interviews — then learns which pitches work
and does more of those. Like its namesake, the messenger of the gods, it
moves fast; like a mesh, its agents stay in constant contact with each
other.

## The three agents

| Agent | Job |
|---|---|
| **Sourcing** | Finds leads (CSV import today; Apollo/web-search providers scaffolded), dedupes, scores, publishes `lead.discovered` |
| **Manager** | Scores & prioritizes leads, enforces compliance (DNC, calling windows, max attempts), dispatches `call.requested` with the current best pitch variant, notifies you on interviews |
| **Voice** (×N) | Pipecat pipeline (Twilio → Deepgram → GPT → Cartesia → Twilio). Opens every call with an AI disclosure, pitches, handles objections, books interviews via tool calls |

They talk **only** through a typed event bus (`agents/bus.py`) — no direct
calls between agent kinds. The **learning loop** scores every call outcome,
picks pitch variants epsilon-greedy, and promotes winners.

## Quickstart (no API keys — full simulation)

```bash
cd mercury-mesh
python3 -m unittest discover -s tests   # 16 tests, stdlib only
PYTHONPATH=. python3 scripts/seed_demo.py  # watch the learning loop crown a winner
```

## Quickstart (real calls)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[voice]"        # pipecat-ai + deepgram/fastapi/twilio extras
cp .env.example .env             # fill in keys
# 1. API + webhooks (expose via ngrok/cloudflared for Twilio)
uvicorn api.server:app --port 8000
# 2. voice worker (run 1..N for concurrent callers)
python scripts/voice_worker.py
# 3. import leads, then start dispatching
curl -F file=@leads.csv localhost:8000/api/leads/import
curl -X POST localhost:8000/api/campaign/start
```

See `ARCHITECTURE.md` for the full design: event catalog, learning math,
compliance rules, cost estimates, and the production roadmap.

## Configuration

- `cp agents/candidate_profile_sample.py agents/candidate_profile.py` and put
  your real details in it. That file is gitignored — only the sample ships.
- `cp .env.example .env` and fill in your API keys. `.env` is gitignored too.

## Compliance

Every call opens with an AI disclosure, calls run 9am–8pm recipient-local on
weekdays only, DNC requests are honored immediately, and each lead is retired
after 4 attempts. This is a starting point, not legal advice — AI
cold-calling is regulated (FCC/TCPA, state AI-disclosure laws). Review with
counsel before real campaigns.
