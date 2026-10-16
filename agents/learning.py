"""The learning loop: figures out what's working and does more of it.

Every call is tagged with the script variant used. Outcomes become rewards
(models.OUTCOME_SCORES). Variant selection is epsilon-greedy with Laplace
smoothing: mostly exploit the current winner, sometimes explore the others
so the system keeps learning instead of freezing on an early lucky streak.

Publishes VARIANT_PROMOTED when a variant takes a clear lead, and emits a
human-readable LEARNING_REPORT for the manager.
"""
from __future__ import annotations

import random
from dataclasses import asdict

from . import models
from .models import OUTCOME_SCORES, Event, ScriptVariant
from .store import Store

DEFAULT_EPSILON = 0.15  # 15% of calls explore non-winning variants


class LearningLoop:
    def __init__(self, store: Store, bus=None, epsilon: float = DEFAULT_EPSILON):
        self.store = store
        self.bus = bus
        self.epsilon = epsilon
        self._last_leader: str | None = None

    # ---- stats ----
    def variant_stats(self) -> dict[str, dict]:
        stats: dict[str, dict] = {}
        for v in self.store.list_variants(active_only=False):
            calls = self.store.calls_for_variant(v.id)
            reward = sum(OUTCOME_SCORES.get(c.outcome, 0.0) for c in calls)
            interviews = sum(1 for c in calls if c.outcome == "interview_booked")
            stats[v.id] = {
                "name": v.name, "calls": len(calls),
                "reward": round(reward, 2),
                "smoothed_rate": (reward + 1) / (len(calls) + 4),  # Laplace
                "interviews": interviews,
            }
        return stats

    def leader(self) -> str | None:
        stats = self.variant_stats()
        cands = [(s["smoothed_rate"], vid) for vid, s in stats.items() if s["calls"] > 0]
        return max(cands)[1] if cands else None

    # ---- selection ----
    def select_variant(self, rng: random.Random | None = None) -> ScriptVariant | None:
        variants = self.store.list_variants(active_only=True)
        if not variants:
            return None
        rng = rng or random
        if rng.random() < self.epsilon or self.leader() is None:
            return rng.choice(variants)  # explore
        return self.store.get_variant(self.leader())  # exploit

    # ---- promotion + reporting ----
    async def maybe_promote(self) -> None:
        lead = self.leader()
        if lead and lead != self._last_leader and self.bus:
            stats = self.variant_stats()[lead]
            if stats["calls"] >= 10:  # don't crown a winner on 2 lucky calls
                self._last_leader = lead
                await self.bus.publish(Event(
                    type=models.VARIANT_PROMOTED,
                    payload={"variant_id": lead, "stats": stats}))

    def report(self) -> str:
        stats = self.variant_stats()
        lines = ["VARIANT PERFORMANCE (reward = interview 1.0 / callback 0.5 / convo 0.25):"]
        for vid, s in sorted(stats.items(), key=lambda kv: -kv[1]["smoothed_rate"]):
            lines.append(
                f"  - {s['name']}: {s['calls']} calls, {s['interviews']} interviews, "
                f"smoothed rate {s['smoothed_rate']:.3f}")
        lead = self.leader()
        if lead:
            lines.append(f"\nCurrent winner: {stats[lead]['name']} "
                         f"({stats[lead]['calls']} calls). Exploiting it "
                         f"{int((1 - self.epsilon) * 100)}% of the time.")
        counts = self.store.outcome_counts()
        total = sum(counts.values())
        if total:
            lines.append("\nOUTCOMES (all variants):")
            for outcome, n in sorted(counts.items(), key=lambda kv: -kv[1]):
                lines.append(f"  - {outcome}: {n} ({n / total:.0%})")
        return "\n".join(lines)

    def propose_variant(self, base: ScriptVariant, tweak: str) -> ScriptVariant:
        """Draft a new experimental variant from a winner. The manager (or a
        human) reviews before it goes live — new variants start active=False
        and are only enabled after approval."""
        return ScriptVariant(
            name=f"{base.name}_exp",
            opener=base.opener,
            pitch=base.pitch + " " + tweak,
            rebuttals=dict(base.rebuttals),
            active=False,
        )

    def snapshot(self) -> dict:
        return {"stats": self.variant_stats(), "leader": self.leader(),
                "report": self.report()}
