"""Core tests: bus, compliance, learning math, manager dispatch, pitch.

Run:  python -m unittest discover -s tests
No API keys, no network, no Pipecat needed.
"""
from __future__ import annotations

import asyncio
import random
import unittest
from dataclasses import asdict
from datetime import datetime
from zoneinfo import ZoneInfo

from agents import compliance, models
from agents.bus import EventBus
from agents.learning import LearningLoop
from agents.manager import ManagerAgent
from agents.models import CallRecord, Event, Lead, ScriptVariant
from agents.profile import build_system_prompt, default_variants, score_lead
from agents.store import Store

CT = ZoneInfo("America/Chicago")


def run(coro):
    return asyncio.run(coro)


class TestBus(unittest.TestCase):
    def test_pubsub(self):
        bus, seen = EventBus(), []
        bus.subscribe("ping", lambda e: seen.append(e.payload["n"]))
        run(bus.publish(Event(type="ping", payload={"n": 1})))
        self.assertEqual(seen, [1])

    def test_broken_subscriber_isolated(self):
        bus, seen = EventBus(), []

        def bad(e):
            raise RuntimeError("boom")

        bus.subscribe("ping", bad)
        bus.subscribe("ping", lambda e: seen.append(1))
        run(bus.publish(Event(type="ping")))
        self.assertEqual(seen, [1])

    def test_wildcard(self):
        bus, seen = EventBus(), []
        bus.subscribe("*", lambda e: seen.append(e.type))
        run(bus.publish(Event(type="a")))
        run(bus.publish(Event(type="b")))
        self.assertEqual(seen, ["a", "b"])


class TestCompliance(unittest.TestCase):
    def test_window_weekday_afternoon(self):
        now = datetime(2026, 10, 13, 14, 0, tzinfo=CT)  # Tue 2pm
        self.assertTrue(compliance.in_calling_window("America/Chicago", now))

    def test_window_late_night(self):
        now = datetime(2026, 10, 13, 22, 0, tzinfo=CT)
        self.assertFalse(compliance.in_calling_window("America/Chicago", now))

    def test_window_weekend(self):
        now = datetime(2026, 10, 17, 14, 0, tzinfo=CT)  # Saturday
        self.assertFalse(compliance.in_calling_window("America/Chicago", now))

    def test_dnc_blocks(self):
        store = Store()
        store.add_dnc("+15550001", "test")
        lead = Lead(name="X", phone="+15550001")
        ok, reason = compliance.check_call_allowed(lead, store)
        self.assertEqual((ok, reason), (False, "dnc_listed"))

    def test_max_attempts_blocks(self):
        store, lead = Store(), Lead(name="X", phone="+15550002", attempts=4)
        ok, reason = compliance.check_call_allowed(
            lead, store, datetime(2026, 10, 13, 14, 0, tzinfo=CT))
        self.assertEqual((ok, reason), (False, "max_attempts"))


class TestLearning(unittest.TestCase):
    def _store_with_calls(self):
        store = Store()
        variants = default_variants()
        for v in variants:
            store.save_variant(v)
        # winner gets 6 interviews / 20 calls; loser gets 1 / 20
        for i, v in enumerate(variants):
            wins = 6 if i == 0 else 1
            for j in range(20):
                outcome = "interview_booked" if j < wins else "no_answer"
                store.save_call(CallRecord(lead_id=f"l{j}", variant_id=v.id,
                                           outcome=outcome))
        return store, variants

    def test_leader_is_winner(self):
        store, variants = self._store_with_calls()
        loop = LearningLoop(store, epsilon=0.0)
        self.assertEqual(loop.leader(), variants[0].id)

    def test_exploit_always_picks_leader(self):
        store, variants = self._store_with_calls()
        loop = LearningLoop(store, epsilon=0.0)
        for _ in range(10):
            self.assertEqual(loop.select_variant(random.Random(1)).id, variants[0].id)

    def test_report_mentions_winner(self):
        store, variants = self._store_with_calls()
        self.assertIn(variants[0].name, LearningLoop(store).report())


class TestProfile(unittest.TestCase):
    def test_prompt_has_disclosure_and_facts(self):
        lead = Lead(name="Jane Recruiter", title="Recruiter", company="Acme")
        prompt = build_system_prompt(lead, default_variants()[0])
        self.assertIn("AI voice assistant", prompt)
        self.assertIn("Uday Varikuppala", prompt)
        self.assertIn("50K+", prompt)
        compliance.assert_disclosure_present(prompt)

    def test_disclosure_assertion_fires(self):
        with self.assertRaises(ValueError):
            compliance.assert_disclosure_present("hello there")

    def test_recruiter_scores_above_plain(self):
        r = score_lead(Lead(title="Technical Recruiter", company="Acme"))
        p = score_lead(Lead(title="Accountant", company="Acme"))
        self.assertGreater(r, p)


class TestManager(unittest.TestCase):
    def test_dispatch_picks_best_and_skips_dnc(self):
        store, bus = Store(), EventBus()
        notified = []
        loop = LearningLoop(store, bus, epsilon=0.0)
        mgr = ManagerAgent(bus, store, loop,
                           notify=lambda t: notified.append(t) or asyncio.sleep(0))
        run(mgr.start())
        for v in default_variants():
            store.save_variant(v)
        dnc_lead = Lead(name="DNC", title="Technical Recruiter", phone="+15550100")
        good_lead = Lead(name="Good", title="Technical Recruiter", phone="+15550101",
                         email="g@x.com")
        for l in (dnc_lead, good_lead):
            store.save_lead(l)
            l.status = "queued"
            store.update_lead(l)
        store.add_dnc("+15550100", "test")
        now = datetime(2026, 10, 13, 14, 0, tzinfo=CT)
        payload = run(mgr.dispatch_next(now=now))
        self.assertIsNotNone(payload)
        self.assertEqual(payload["lead"]["phone"], "+15550101")

    def test_interview_end_to_end(self):
        store, bus = Store(), EventBus()
        notified = []

        async def notify(t):
            notified.append(t)

        loop = LearningLoop(store, bus, epsilon=0.0)
        mgr = ManagerAgent(bus, store, loop, notify=notify)
        run(mgr.start())
        v = default_variants()[0]
        store.save_variant(v)
        lead = Lead(name="Jane", title="Recruiter", company="Acme", phone="+15550200")
        store.save_lead(lead)
        call = CallRecord(lead_id=lead.id, variant_id=v.id, outcome="interview_booked")
        run(bus.publish(Event(type=models.CALL_ENDED, payload={"call": asdict(call)})))
        run(bus.publish(Event(type=models.INTERVIEW_BOOKED,
                              payload={"lead_id": lead.id, "name": "Jane",
                                       "title": "Recruiter", "company": "Acme",
                                       "when": "Tue 2pm", "notes": ""})))
        self.assertEqual(store.get_lead(lead.id).status, "interview")
        self.assertTrue(any("INTERVIEW BOOKED" in n for n in notified))


if __name__ == "__main__":
    unittest.main()
