"""Offline demo: proves the manager + learning loop work with zero API keys.

Seeds 3 pitch variants and 24 fake leads, then simulates 150 calls where
each variant has a different TRUE interview rate. The learning loop should
discover the winner and concentrate calls on it.

Run:  python scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import random
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from agents import models
from agents.bus import EventBus
from agents.learning import LearningLoop
from agents.manager import ManagerAgent
from agents.models import CallRecord, Event, Lead
from agents.profile import default_variants
from agents.store import Store

# Ground truth the learning loop must discover (unknown to the agents).
TRUE_RATES = {
    "results_opener": {"interview": 0.04, "callback": 0.06, "conversation": 0.15},
    "problem_opener": {"interview": 0.12, "callback": 0.10, "conversation": 0.20},
    "referral_opener": {"interview": 0.07, "callback": 0.08, "conversation": 0.16},
}

NAMES = ["Ava Recruiter", "Liam Talent", "Maya Hiring", "Noah Staffing", "Emma People",
         "Olivia Search", "Ethan HR", "Sophia Recruit", "James Vendor", "Isabella Hire"]


def fake_leads(n: int = 24) -> list[Lead]:
    leads = []
    titles = ["Technical Recruiter", "Hiring Manager", "Talent Sourcer",
              "Staffing Vendor", "HR Business Partner"]
    for i in range(n):
        leads.append(Lead(
            name=f"{NAMES[i % len(NAMES)]} {i}",
            title=titles[i % len(titles)],
            company=f"Company {i % 6}",
            phone=f"+1555000{i:04d}",
            email=f"lead{i}@example.com",
            timezone="America/Chicago",
            source="demo",
        ))
    return leads


def simulate_call(rng: random.Random, variant_name: str) -> str:
    r = TRUE_RATES[variant_name]
    x = rng.random()
    if x < r["interview"]:
        return "interview_booked"
    if x < r["interview"] + r["callback"]:
        return "callback_requested"
    if x < r["interview"] + r["callback"] + r["conversation"]:
        return "conversation"
    return rng.choice(["no_answer", "no_answer", "voicemail", "rejected"])


async def main() -> None:
    rng = random.Random(7)
    store, bus = Store(), EventBus()
    learning = LearningLoop(store, bus, epsilon=0.2)
    manager = ManagerAgent(bus, store, learning, rng=rng)
    await manager.start()

    variants = {v.name: v for v in default_variants()}
    for v in variants.values():
        store.save_variant(v)
    for lead in fake_leads():
        store.save_lead(lead)
        lead.status = "queued"
        store.update_lead(lead)

    # Tuesday 2pm CT: inside the compliance calling window.
    now = datetime(2026, 10, 13, 14, 0, tzinfo=ZoneInfo("America/Chicago"))

    dispatched = 0
    for _ in range(150):
        payload = await manager.dispatch_next(now=now)
        if not payload:
            break
        dispatched += 1
        lead = Lead(**payload["lead"])
        variant = variants[payload["variant"]["name"]]
        outcome = simulate_call(rng, variant.name)
        call = CallRecord(
            lead_id=lead.id, variant_id=variant.id, outcome=outcome,
            duration_s=rng.uniform(20, 180),
            summary=f"demo call -> {outcome}",
        )
        await bus.publish(Event(type=models.CALL_ENDED, payload={"call": asdict(call)}))

    print(f"dispatched {dispatched} calls\n")
    print(learning.report())
    print(f"\nTrue best variant: problem_opener | Learned winner: "
          f"{learning.variant_stats().get(learning.leader() or '', {}).get('name')}")


if __name__ == "__main__":
    asyncio.run(main())
