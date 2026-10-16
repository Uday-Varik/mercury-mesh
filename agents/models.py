"""Shared data models and the inter-agent event catalog.

This file is the contract every agent speaks. The EventBus carries Events;
agents never call each other directly.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


def new_id(prefix: str = "") -> str:
    return f"{prefix}{uuid.uuid4().hex[:12]}"


def now_ts() -> float:
    return time.time()


class Outcome(str, Enum):
    INTERVIEW_BOOKED = "interview_booked"
    CALLBACK_REQUESTED = "callback_requested"
    CONVERSATION = "conversation"      # real talk, no commitment yet
    VOICEMAIL = "voicemail"
    NO_ANSWER = "no_answer"
    REJECTED = "rejected"
    WRONG_NUMBER = "wrong_number"
    DNC_REQUESTED = "dnc_requested"


# Learning-loop reward per outcome. Interview booked = full win.
OUTCOME_SCORES = {
    Outcome.INTERVIEW_BOOKED: 1.0,
    Outcome.CALLBACK_REQUESTED: 0.5,
    Outcome.CONVERSATION: 0.25,
    Outcome.VOICEMAIL: 0.05,
    Outcome.NO_ANSWER: 0.0,
    Outcome.REJECTED: 0.0,
    Outcome.WRONG_NUMBER: 0.0,
    Outcome.DNC_REQUESTED: 0.0,
}


class LeadStatus(str, Enum):
    NEW = "new"
    QUEUED = "queued"
    CONTACTED = "contacted"
    CALLBACK = "callback"
    INTERVIEW = "interview"
    DEAD = "dead"          # rejected / wrong number / dnc
    EXHAUSTED = "exhausted"  # max attempts reached


@dataclass
class Lead:
    id: str = field(default_factory=lambda: new_id("lead_"))
    name: str = ""
    title: str = ""
    company: str = ""
    phone: str = ""
    email: str = ""
    source: str = ""
    score: float = 0.0
    status: str = LeadStatus.NEW.value
    timezone: str = "America/Chicago"
    notes: str = ""
    attempts: int = 0
    last_attempt_at: float | None = None
    created_at: float = field(default_factory=now_ts)


@dataclass
class CallRecord:
    id: str = field(default_factory=lambda: new_id("call_"))
    lead_id: str = ""
    variant_id: str = ""
    outcome: str = Outcome.NO_ANSWER.value
    started_at: float = field(default_factory=now_ts)
    ended_at: float = field(default_factory=now_ts)
    duration_s: float = 0.0
    transcript: str = ""
    summary: str = ""
    recording_url: str = ""


@dataclass
class ScriptVariant:
    """One pitch script the voice agents can run. The learning loop
    scores variants and promotes winners."""
    id: str = field(default_factory=lambda: new_id("var_"))
    name: str = ""
    opener: str = ""
    pitch: str = ""
    rebuttals: dict = field(default_factory=dict)
    active: bool = True
    created_at: float = field(default_factory=now_ts)


@dataclass
class Event:
    type: str
    payload: dict = field(default_factory=dict)
    ts: float = field(default_factory=now_ts)
    correlation_id: str = field(default_factory=lambda: new_id("evt_"))


# ---- Event catalog -------------------------------------------------
LEAD_DISCOVERED = "lead.discovered"    # sourcing -> manager   {lead: dict}
LEAD_SCORED = "lead.scored"            # manager  -> bus       {lead_id, score}
CALL_REQUESTED = "call.requested"      # manager  -> voice pool {lead: dict, variant: dict}
CALL_STARTED = "call.started"          # voice    -> bus       {call_id, lead_id, variant_id}
CALL_ENDED = "call.ended"              # voice    -> manager   {call: dict}
INTERVIEW_BOOKED = "interview.booked"  # voice    -> manager   {lead_id, when, notes}
DNC_ADDED = "dnc.added"                # voice    -> bus       {phone, reason}
VARIANT_PROMOTED = "variant.promoted"  # learning -> bus       {variant_id, stats}
LEARNING_REPORT = "learning.report"    # learning -> manager   {report: str}
