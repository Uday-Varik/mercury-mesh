"""Legal/safety guardrails. EVERY outbound call passes through here.

v1 rules (US-focused, conservative):
  - The agent must disclose it is AI at the start of every call.
  - Calls only 9am-8pm in the *recipient's* local timezone, Mon-Fri.
  - Do-not-call list is hard-blocked. A DNC request during a call adds the
    number immediately and the call ends.
  - Max 4 attempts per lead, then the lead is retired.

This is not legal advice. AI cold-calling rules (FCC/TCPA, state AI
disclosure laws) change and vary by jurisdiction — review with counsel
before running real campaigns.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CANDIDATE_NAME = "Uday Varikuppala"

CALL_WINDOW_START = 9   # 9am recipient-local
CALL_WINDOW_END = 20    # 8pm recipient-local
MAX_ATTEMPTS = 4


def disclosure_line(lead_name: str = "") -> str:
    first = (lead_name or "").split()[0] or "there"
    return (
        f"Hi {first}, this is an AI voice assistant calling on behalf of "
        f"{CANDIDATE_NAME} about a potential job fit. Just to be upfront, "
        f"you're speaking with an AI, not a person. Is now an okay time for "
        f"a quick two-minute chat?"
    )


def _tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name or "America/Chicago")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("America/Chicago")


def in_calling_window(tz_name: str, now: datetime | None = None) -> bool:
    tz = _tz(tz_name)
    now = now or datetime.now(tz)
    local = now.astimezone(tz)
    if local.weekday() >= 5:      # no weekend calls in v1
        return False
    return CALL_WINDOW_START <= local.hour < CALL_WINDOW_END


def check_call_allowed(lead, store, now: datetime | None = None) -> tuple[bool, str]:
    """Gate every outbound dial. Returns (allowed, reason)."""
    if store.is_dnc(lead.phone):
        return False, "dnc_listed"
    if lead.attempts >= MAX_ATTEMPTS:
        return False, "max_attempts"
    if not in_calling_window(lead.timezone, now):
        return False, "outside_calling_window"
    if not lead.phone:
        return False, "no_phone"
    return True, "ok"


def assert_disclosure_present(system_prompt: str) -> None:
    """Fail fast if a voice-agent prompt somehow lost its AI disclosure."""
    lowered = system_prompt.lower()
    must = ["ai voice assistant", "speaking with an ai"]
    if not all(m in lowered for m in must):
        raise ValueError("Voice agent prompt is missing the mandatory AI disclosure.")
