"""Voice worker: consumes CALL_REQUESTED and dials.

Run:  python scripts/voice_worker.py
Run N of these for N concurrent callers. Each worker:
  1. subscribes to CALL_REQUESTED on the bus
  2. dials via Twilio REST (place_outbound_call)
  3. Twilio streams audio to /ws/twilio/{token} -> Pipecat pipeline runs

For multi-machine scale, point every worker at the same Redis-backed bus
(see ARCHITECTURE.md) and the same Postgres store.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agents import models
from agents.bus import EventBus
from agents.models import Event
from agents.store import Store
from agents.voice_agent import place_outbound_call

bus = EventBus()
store = Store(os.environ.get("DATABASE_PATH", "mercury-mesh.db"))

HTTP_BASE = os.environ.get("PUBLIC_HTTP_URL", "https://YOUR_HOST")
FROM_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "")


async def on_call_requested(event: Event) -> None:
    lead, variant = event.payload["lead"], event.payload["variant"]
    try:
        token = place_outbound_call(lead, variant, http_base=HTTP_BASE,
                                    from_number=FROM_NUMBER)
        print(f"dialing {lead['name']} @ {lead['phone']} (token {token})")
    except Exception as e:  # never let one bad dial kill the worker
        print(f"dial failed for {lead.get('phone')}: {e}")


async def main() -> None:
    bus.subscribe(models.CALL_REQUESTED, on_call_requested)
    print("voice worker up — waiting for CALL_REQUESTED")
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
