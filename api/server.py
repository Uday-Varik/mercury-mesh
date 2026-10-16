"""HTTP API + Twilio webhook + dashboard.

Run:  uvicorn api.server:app --host 0.0.0.0 --port 8000

Twilio setup (outbound):
  1. Buy a number in the Twilio console, set its voice webhook to
     POST https://YOUR_HOST/voice/twilio
  2. POST /api/campaign/start -> manager dispatches CALL_REQUESTED ->
     voice worker dials via Twilio REST with the /voice/twilio webhook ->
     Twilio opens a media stream to /ws/twilio -> Pipecat pipeline runs.

Env: see .env.example
"""
from __future__ import annotations

import os
from dataclasses import asdict

from fastapi import FastAPI, UploadFile, WebSocket
from fastapi.responses import PlainTextResponse

from agents import models
from agents.bus import EventBus
from agents.learning import LearningLoop
from agents.manager import ManagerAgent
from agents.models import Event, Lead
from agents.profile import default_variants
from agents.sourcing import CsvLeadProvider, SourcingAgent
from agents.store import Store

PUBLIC_WS_URL = os.environ.get("PUBLIC_WS_URL", "wss://YOUR_HOST/ws/twilio")

store = Store(os.environ.get("DATABASE_PATH", "mercury-mesh.db"))
bus = EventBus()
learning = LearningLoop(store, bus)
manager = ManagerAgent(bus, store, learning)
sourcing = SourcingAgent(bus, store, [])

for v in default_variants():
    if not store.get_variant(v.id):
        store.save_variant(v)

app = FastAPI(title="mercury-mesh")


@app.on_event("startup")
async def _startup() -> None:
    await manager.start()


# ---- campaign control ----
@app.post("/api/leads/import")
async def import_leads(file: UploadFile):
    path = f"/tmp/{file.filename}"
    with open(path, "wb") as f:
        f.write(await file.read())
    sourcing.providers.append(CsvLeadProvider(path))
    leads = await sourcing.discover("import")
    return {"imported": len(leads)}


@app.get("/api/leads")
def list_leads(status: str | None = None):
    return [asdict(l) for l in store.list_leads(status=status)]


@app.get("/api/dashboard")
def dashboard():
    return {
        "outcome_counts": store.outcome_counts(),
        "learning": learning.snapshot(),
    }


@app.get("/api/learning/report")
def learning_report():
    return {"report": learning.report()}


@app.post("/api/campaign/start")
async def campaign_start():
    """Dispatch one call right now (the voice worker pool consumes
    CALL_REQUESTED continuously in production)."""
    payload = await manager.dispatch_next()
    return {"dispatched": payload is not None, "payload": payload}


@app.get("/api/summary")
def summary():
    return {"summary": manager.daily_summary()}


# ---- Twilio voice webhook ----
# The voice worker dials with url=/voice/twilio/{token}; the token maps the
# incoming media stream back to the (lead, variant) it was dispatched for.
@app.post("/voice/twilio/{token}")
def twilio_voice(token: str):
    from agents.voice_agent import twiml_for_token
    return PlainTextResponse(twiml_for_token(token, PUBLIC_WS_URL),
                             media_type="text/xml")


@app.websocket("/ws/twilio/{token}")
async def twilio_stream(ws: WebSocket, token: str):
    """Twilio Media Stream lands here; hand the socket to the Pipecat agent."""
    await ws.accept()
    from agents.voice_agent import run_pipeline_over_websocket
    await run_pipeline_over_websocket(ws, token, bus, store)
