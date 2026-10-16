"""Shared state: the system's CRM.

SQLite for v1 (zero dependencies, works everywhere). The Store API is the
only thing agents touch, so it can be swapped for Postgres later without
changing any agent code.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import asdict
from typing import Optional

from .models import CallRecord, Lead, ScriptVariant, now_ts

_SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id TEXT PRIMARY KEY, name TEXT, title TEXT, company TEXT, phone TEXT,
    email TEXT, source TEXT, score REAL, status TEXT, timezone TEXT,
    notes TEXT, attempts INTEGER, last_attempt_at REAL, created_at REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY, lead_id TEXT, variant_id TEXT, outcome TEXT,
    started_at REAL, ended_at REAL, duration_s REAL,
    transcript TEXT, summary TEXT, recording_url TEXT
);
CREATE INDEX IF NOT EXISTS idx_calls_variant ON calls(variant_id);
CREATE INDEX IF NOT EXISTS idx_calls_lead ON calls(lead_id);
CREATE TABLE IF NOT EXISTS variants (
    id TEXT PRIMARY KEY, name TEXT, opener TEXT, pitch TEXT,
    rebuttals TEXT, active INTEGER, created_at REAL
);
CREATE TABLE IF NOT EXISTS dnc (
    phone TEXT PRIMARY KEY, reason TEXT, added_at REAL
);
"""


def _lead_from_row(r: sqlite3.Row) -> Lead:
    d = dict(r)
    return Lead(**d)


def _call_from_row(r: sqlite3.Row) -> CallRecord:
    return CallRecord(**dict(r))


def _variant_from_row(r: sqlite3.Row) -> ScriptVariant:
    d = dict(r)
    d["rebuttals"] = json.loads(d["rebuttals"] or "{}")
    d["active"] = bool(d["active"])
    return ScriptVariant(**d)


class Store:
    def __init__(self, path: str = ":memory:") -> None:
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(_SCHEMA)

    # ---- leads ----
    def save_lead(self, lead: Lead) -> Lead:
        """Upsert keyed on phone: re-sourcing the same number updates, not dupes."""
        with self._lock:
            cur = self._db.execute("SELECT id FROM leads WHERE phone = ?", (lead.phone,))
            if cur.fetchone():
                self._db.execute(
                    """UPDATE leads SET name=?, title=?, company=?, email=?, source=?,
                       score=?, notes=? WHERE phone=?""",
                    (lead.name, lead.title, lead.company, lead.email, lead.source,
                     lead.score, lead.notes, lead.phone),
                )
            else:
                self._db.execute(
                    """INSERT INTO leads VALUES
                       (:id,:name,:title,:company,:phone,:email,:source,:score,:status,
                        :timezone,:notes,:attempts,:last_attempt_at,:created_at)""",
                    asdict(lead),
                )
            self._db.commit()
        return lead

    def get_lead(self, lead_id: str) -> Optional[Lead]:
        with self._lock:
            cur = self._db.execute("SELECT * FROM leads WHERE id=?", (lead_id,))
            row = cur.fetchone()
        return _lead_from_row(row) if row else None

    def list_leads(self, status: str | None = None, limit: int = 500) -> list[Lead]:
        with self._lock:
            if status:
                cur = self._db.execute(
                    "SELECT * FROM leads WHERE status=? ORDER BY score DESC LIMIT ?",
                    (status, limit),
                )
            else:
                cur = self._db.execute(
                    "SELECT * FROM leads ORDER BY score DESC LIMIT ?", (limit,))
            return [_lead_from_row(r) for r in cur.fetchall()]

    def update_lead(self, lead: Lead) -> None:
        with self._lock:
            self._db.execute(
                """UPDATE leads SET name=:name, title=:title, company=:company,
                   email=:email, score=:score, status=:status, timezone=:timezone,
                   notes=:notes, attempts=:attempts, last_attempt_at=:last_attempt_at
                   WHERE id=:id""",
                asdict(lead),
            )
            self._db.commit()

    # ---- calls ----
    def save_call(self, call: CallRecord) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO calls VALUES (:id,:lead_id,:variant_id,:outcome,:started_at,"
                ":ended_at,:duration_s,:transcript,:summary,:recording_url)",
                asdict(call),
            )
            self._db.commit()

    def calls_for_variant(self, variant_id: str) -> list[CallRecord]:
        with self._lock:
            cur = self._db.execute("SELECT * FROM calls WHERE variant_id=?", (variant_id,))
            return [_call_from_row(r) for r in cur.fetchall()]

    def recent_calls(self, limit: int = 200) -> list[CallRecord]:
        with self._lock:
            cur = self._db.execute(
                "SELECT * FROM calls ORDER BY ended_at DESC LIMIT ?", (limit,))
            return [_call_from_row(r) for r in cur.fetchall()]

    def outcome_counts(self) -> dict[str, int]:
        with self._lock:
            cur = self._db.execute("SELECT outcome, COUNT(*) c FROM calls GROUP BY outcome")
            return {r["outcome"]: r["c"] for r in cur.fetchall()}

    # ---- variants ----
    def save_variant(self, v: ScriptVariant) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO variants VALUES (?,?,?,?,?,?,?)",
                (v.id, v.name, v.opener, v.pitch, json.dumps(v.rebuttals),
                 int(v.active), v.created_at),
            )
            self._db.commit()

    def list_variants(self, active_only: bool = True) -> list[ScriptVariant]:
        with self._lock:
            q = "SELECT * FROM variants" + (" WHERE active=1" if active_only else "")
            cur = self._db.execute(q)
            return [_variant_from_row(r) for r in cur.fetchall()]

    def get_variant(self, variant_id: str) -> Optional[ScriptVariant]:
        with self._lock:
            cur = self._db.execute("SELECT * FROM variants WHERE id=?", (variant_id,))
            row = cur.fetchone()
        return _variant_from_row(row) if row else None

    # ---- do-not-call ----
    def add_dnc(self, phone: str, reason: str = "") -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO dnc VALUES (?,?,?)", (phone, reason, now_ts()))
            self._db.commit()

    def is_dnc(self, phone: str) -> bool:
        with self._lock:
            cur = self._db.execute("SELECT 1 FROM dnc WHERE phone=?", (phone,))
            return cur.fetchone() is not None
