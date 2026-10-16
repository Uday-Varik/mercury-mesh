"""Manager agent: the conductor of the whole operation.

Responsibilities:
  - scores incoming leads (LEAD_DISCOVERED) and queues them
  - picks the next best lead, checks compliance, asks the learning loop
    which script variant to use, and publishes CALL_REQUESTED for the
    voice-agent pool
  - consumes CALL_ENDED: persists the call, updates lead status, feeds the
    learning loop, and notifies the human on interviews
  - enforces DNC immediately

The manager never dials anything itself — voice workers consume
CALL_REQUESTED independently, so you can scale from 1 to N callers.
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import asdict
from datetime import datetime
from typing import Awaitable, Callable, Optional

from . import compliance, models
from .bus import EventBus
from .models import CallRecord, Event, Lead, LeadStatus
from .learning import LearningLoop
from .profile import score_lead
from .store import Store

NotifyFn = Callable[[str], Awaitable[None]]

RETRYABLE = {LeadStatus.NEW.value, LeadStatus.QUEUED.value,
             LeadStatus.CONTACTED.value, LeadStatus.CALLBACK.value}


async def _default_notify(text: str) -> None:
    print(f"[notify] {text}")


class ManagerAgent:
    def __init__(self, bus: EventBus, store: Store, learning: LearningLoop,
                 notify: NotifyFn | None = None, rng: random.Random | None = None):
        self.bus = bus
        self.store = store
        self.learning = learning
        self.notify = notify or _default_notify
        self.rng = rng or random.Random()

    async def start(self) -> None:
        self.bus.subscribe(models.LEAD_DISCOVERED, self._on_lead_discovered)
        self.bus.subscribe(models.CALL_ENDED, self._on_call_ended)
        self.bus.subscribe(models.INTERVIEW_BOOKED, self._on_interview_booked)
        self.bus.subscribe(models.DNC_ADDED, self._on_dnc_added)

    # ---- event handlers ----
    async def _on_lead_discovered(self, event: Event) -> None:
        lead = Lead(**event.payload["lead"])
        lead.score = score_lead(lead)
        lead.status = LeadStatus.QUEUED.value
        self.store.update_lead(lead)
        await self.bus.publish(Event(type=models.LEAD_SCORED,
                                     payload={"lead_id": lead.id, "score": lead.score}))

    async def _on_call_ended(self, event: Event) -> None:
        call = CallRecord(**event.payload["call"])
        self.store.save_call(call)
        lead = self.store.get_lead(call.lead_id)
        if lead:
            lead.last_attempt_at = call.ended_at
            lead.status = self._next_status(lead, call.outcome)
            self.store.update_lead(lead)
            if call.outcome == "dnc_requested":
                self.store.add_dnc(lead.phone, "requested on call")
        await self.learning.maybe_promote()

    async def _on_interview_booked(self, event: Event) -> None:
        p = event.payload
        await self.notify(
            f"INTERVIEW BOOKED with {p.get('name')} ({p.get('title')} @ "
            f"{p.get('company')}) — {p.get('when')}. Notes: {p.get('notes', '')}")

    async def _on_dnc_added(self, event: Event) -> None:
        self.store.add_dnc(event.payload["phone"], event.payload.get("reason", ""))

    # ---- dispatch ----
    @staticmethod
    def _next_status(lead: Lead, outcome: str) -> str:
        if outcome == "interview_booked":
            return LeadStatus.INTERVIEW.value
        if outcome == "callback_requested":
            return LeadStatus.CALLBACK.value
        if outcome in ("rejected", "wrong_number", "dnc_requested"):
            return LeadStatus.DEAD.value
        if lead.attempts >= compliance.MAX_ATTEMPTS:
            return LeadStatus.EXHAUSTED.value
        return LeadStatus.CONTACTED.value

    async def dispatch_next(self, now: datetime | None = None) -> Optional[dict]:
        """Pick the best callable lead and request a call. Returns the
        CALL_REQUESTED payload, or None if nothing is dispatchable."""
        candidates = [l for l in self.store.list_leads()
                      if l.status in RETRYABLE]
        for lead in candidates:
            allowed, reason = compliance.check_call_allowed(lead, self.store, now)
            if not allowed:
                if reason in ("max_attempts",):
                    lead.status = LeadStatus.EXHAUSTED.value
                    self.store.update_lead(lead)
                continue
            variant = self.learning.select_variant(self.rng)
            if variant is None:
                return None
            lead.attempts += 1
            lead.status = LeadStatus.QUEUED.value
            self.store.update_lead(lead)
            payload = {"lead": asdict(lead), "variant": asdict(variant)}
            await self.bus.publish(Event(type=models.CALL_REQUESTED, payload=payload))
            return payload
        return None

    async def run(self, poll_seconds: int = 10,
                  stop_after_idle: int | None = None) -> None:
        """Main loop: keep the voice pool fed. stop_after_idle ends the loop
        after N consecutive polls with nothing to dispatch (useful for tests)."""
        idle = 0
        while True:
            got = await self.dispatch_next()
            idle = 0 if got else idle + 1
            if stop_after_idle is not None and idle >= stop_after_idle:
                return
            await asyncio.sleep(poll_seconds)

    def daily_summary(self) -> str:
        counts = self.store.outcome_counts()
        total = sum(counts.values())
        queued = len(self.store.list_leads(status=LeadStatus.QUEUED.value))
        lines = [f"CAMPAIGN SUMMARY — {total} calls placed, {queued} leads queued."]
        for outcome, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            lines.append(f"  {outcome}: {n}")
        lines.append("")
        lines.append(self.learning.report())
        return "\n".join(lines)
