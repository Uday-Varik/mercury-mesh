"""Voice agent: the Pipecat-based caller.

One outbound call = one VoiceSession = one Pipecat pipeline::

    Twilio media stream -> Deepgram STT -> OpenAI LLM (+ tools)
        -> Cartesia TTS -> Twilio

The session's tools publish the inter-agent events (CALL_STARTED /
CALL_ENDED / INTERVIEW_BOOKED / DNC_ADDED) so the manager and the learning
loop stay in sync with every call.

Outbound dialing flow (production):
  1. manager publishes CALL_REQUESTED on the bus
  2. voice worker (scripts/voice_worker.py) calls place_outbound_call():
     mints a token, stashes (lead, variant), dials via Twilio REST with the
     voice webhook /voice/twilio/{token}
  3. Twilio hits the webhook -> we return TwiML <Stream> to
     wss://HOST/ws/twilio/{token}
  4. FastAPI route /ws/twilio/{token} -> run_pipeline_over_websocket()

Env needed for real calls: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN,
TWILIO_PHONE_NUMBER, DEEPGRAM_API_KEY, OPENAI_API_KEY, CARTESIA_API_KEY,
PUBLIC_HTTP_URL, PUBLIC_WS_URL.

All Pipecat imports are lazy so the rest of the system (bus, manager,
learning, tests) runs with zero heavy dependencies.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import asdict
from typing import Optional

from . import compliance, models
from .models import CallRecord, Event, Lead, ScriptVariant
from .profile import build_system_prompt

# token -> {"lead": dict, "variant": dict}; populated by place_outbound_call,
# consumed by the /ws/twilio/{token} route.
PENDING: dict[str, dict] = {}


def _token() -> str:
    return uuid.uuid4().hex[:16]


# --------------------------------------------------------------------------
# Outbound dialing (Twilio REST)
# --------------------------------------------------------------------------
def place_outbound_call(lead: dict, variant: dict, *, http_base: str,
                        from_number: str, twilio_client=None) -> str:
    """Dial a lead. Returns the token that will identify the media stream."""
    if twilio_client is None:
        from twilio.rest import Client  # lazy: only needed for real calls
        twilio_client = Client(os.environ["TWILIO_ACCOUNT_SID"],
                               os.environ["TWILIO_AUTH_TOKEN"])
    token = _token()
    PENDING[token] = {"lead": lead, "variant": variant,
                      "requested_at": time.time()}
    twilio_client.calls.create(
        to=lead["phone"],
        from_=from_number,
        url=f"{http_base}/voice/twilio/{token}",
        machine_detection="Enable",  # don't pitch to voicemail as if live
    )
    return token


def twiml_for_token(token: str, ws_base: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<Response><Connect><Stream url="{ws_base}/ws/twilio/{token}">'
        f'<Parameter name="token" value="{token}"/>'
        "</Stream></Connect></Response>"
    )


# --------------------------------------------------------------------------
# The call session: tools + outcome tracking
# --------------------------------------------------------------------------
class VoiceSession:
    """State for one call. Tool handlers mutate this; finalize() emits CALL_ENDED."""

    def __init__(self, lead: Lead, variant: ScriptVariant, bus, store) -> None:
        self.lead = lead
        self.variant = variant
        self.bus = bus
        self.store = store
        self.call_id = f"call_{uuid.uuid4().hex[:12]}"
        self.started_at = time.time()
        self.final_outcome: Optional[str] = None
        self.summary = ""
        self.task = None  # set once the PipelineTask exists

    @property
    def opener_text(self) -> str:
        # Disclosure first, then the variant opener. Spoken via TTS directly
        # (TTSSpeakFrame) so it never pollutes the LLM context.
        return compliance.disclosure_line(self.lead.name) + " " + self.variant.opener

    # ---- tool handlers (Pipecat FunctionCallParams) ----
    async def _finish(self, outcome: str, summary: str = "") -> None:
        from pipecat.frames.frames import EndFrame
        self.final_outcome = outcome
        if summary:
            self.summary = summary
        if self.task is not None:
            await self.task.queue_frame(EndFrame())

    async def tool_end_call(self, params) -> None:
        outcome = params.arguments.get("outcome", "no_answer")
        summary = params.arguments.get("summary", "")
        await params.result_callback({"status": "ending_call", "outcome": outcome})
        await self._finish(outcome, summary)

    async def tool_book_interview(self, params) -> None:
        when = params.arguments.get("when", "")
        notes = params.arguments.get("notes", "")
        await self.bus.publish(Event(type=models.INTERVIEW_BOOKED, payload={
            "lead_id": self.lead.id, "name": self.lead.name,
            "title": self.lead.title, "company": self.lead.company,
            "when": when, "notes": notes}))
        await params.result_callback({"status": "booked", "when": when})
        await self._finish("interview_booked",
                           f"Interview booked for {when}. {notes}".strip())

    async def tool_request_callback(self, params) -> None:
        when = params.arguments.get("when", "")
        notes = params.arguments.get("notes", "")
        await params.result_callback({"status": "callback_noted", "when": when})
        await self._finish("callback_requested",
                           f"Callback requested {when}. {notes}".strip())

    async def tool_add_to_dnc(self, params) -> None:
        reason = params.arguments.get("reason", "")
        await self.bus.publish(Event(type=models.DNC_ADDED, payload={
            "phone": self.lead.phone, "reason": reason}))
        await params.result_callback({"status": "removed"})
        await self._finish("dnc_requested", f"Added to DNC: {reason}")

    def build_tools(self) -> list:
        from pipecat.adapters.schemas.function_schema import FunctionSchema
        return [
            FunctionSchema(
                name="end_call_with_outcome",
                description=("End the call, reporting what happened. ALWAYS call this "
                             "exactly once when the call is over."),
                properties={
                    "outcome": {"type": "string", "enum": [
                        "interview_booked", "callback_requested", "conversation",
                        "voicemail", "no_answer", "rejected", "wrong_number"]},
                    "summary": {"type": "string",
                                "description": "One-line summary of the call."},
                },
                required=["outcome"],
                handler=self.tool_end_call,
            ),
            FunctionSchema(
                name="book_interview",
                description=("The contact agreed to an interview or intro call. "
                             "Record when, then confirm it back and end politely."),
                properties={
                    "when": {"type": "string",
                             "description": "Agreed date/time, ISO or natural language."},
                    "notes": {"type": "string"},
                },
                required=["when"],
                handler=self.tool_book_interview,
            ),
            FunctionSchema(
                name="request_callback",
                description="They want a callback later instead of talking now.",
                properties={"when": {"type": "string"}, "notes": {"type": "string"}},
                required=[],
                handler=self.tool_request_callback,
            ),
            FunctionSchema(
                name="add_to_dnc",
                description=("They asked not to be called again. Apologize, call "
                             "this immediately, then end the call."),
                properties={"reason": {"type": "string"}},
                required=[],
                handler=self.tool_add_to_dnc,
            ),
        ]

    async def finalize(self) -> CallRecord:
        ended = time.time()
        call = CallRecord(
            id=self.call_id, lead_id=self.lead.id, variant_id=self.variant.id,
            outcome=self.final_outcome or "no_answer",
            started_at=self.started_at, ended_at=ended,
            duration_s=round(ended - self.started_at, 1),
            summary=self.summary,
        )
        await self.bus.publish(Event(type=models.CALL_ENDED,
                                     payload={"call": asdict(call)}))
        return call


# --------------------------------------------------------------------------
# Pipeline runner (Twilio media stream -> Pipecat)
# --------------------------------------------------------------------------
async def run_pipeline_over_websocket(websocket, token: str, bus, store) -> None:
    """Entry point for the FastAPI /ws/twilio/{token} route."""
    payload = PENDING.pop(token, None)
    if payload is None:
        await websocket.close(code=4404)
        return
    lead = Lead(**payload["lead"])
    variant = ScriptVariant(**payload["variant"])
    session = VoiceSession(lead, variant, bus, store)

    from pipecat.pipeline.pipeline import Pipeline
    from pipecat.pipeline.runner import PipelineRunner
    from pipecat.pipeline.task import PipelineParams, PipelineTask
    from pipecat.processors.aggregators.llm_context import LLMContext
    from pipecat.processors.aggregators.llm_response_universal import (
        LLMContextAggregatorPair)
    from pipecat.serializers.twilio import TwilioFrameSerializer
    from pipecat.services.cartesia.tts import CartesiaTTSService
    from pipecat.services.deepgram.stt import DeepgramSTTService
    from pipecat.services.openai.llm import OpenAILLMService
    from pipecat.transports.websocket.fastapi import (
        FastAPIWebsocketParams, FastAPIWebsocketTransport)
    from pipecat.frames.frames import TTSSpeakFrame

    transport = FastAPIWebsocketTransport(
        websocket,
        FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            serializer=TwilioFrameSerializer(websocket),
        ),
    )
    stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
    llm = OpenAILLMService(api_key=os.environ["OPENAI_API_KEY"],
                           model="gpt-4o-mini")
    tts = CartesiaTTSService(api_key=os.environ["CARTESIA_API_KEY"],
                             voice_id=os.environ.get("CARTESIA_VOICE_ID", ""))

    system_prompt = build_system_prompt(lead, variant)  # asserts AI disclosure
    context = LLMContext(
        messages=[{"role": "system", "content": system_prompt}],
        tools=session.build_tools(),
    )
    pair = LLMContextAggregatorPair(context)

    pipeline = Pipeline([
        transport.input(),
        stt,
        pair.user(),
        llm,
        tts,
        pair.assistant(),
        transport.output(),
    ])
    task = PipelineTask(pipeline, params=PipelineParams(
        allow_interruptions=True, enable_metrics=True))
    session.task = task

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        await bus.publish(Event(type=models.CALL_STARTED, payload={
            "call_id": session.call_id, "lead_id": lead.id,
            "variant_id": variant.id}))
        # Bot speaks first: disclosure + opener, straight to TTS.
        await task.queue_frames([TTSSpeakFrame(session.opener_text)])

    runner = PipelineRunner()
    try:
        await runner.run(task)
    finally:
        await session.finalize()
