"""Optional auto-run of the simulation clock (ONE asyncio task, one worker).

The clock is paused by default. When a coordinator presses Start, this task advances simulated time every
TICK_SECONDS by (speed x TICK_SECONDS) simulated minutes, using the same clock.advance() as the manual
buttons, so event processing stays chronological and deterministic (same seed, same events).
It can pause itself when a new HIGH/CRITICAL coordinator alert appears, so the presenter can react.
"""
from __future__ import annotations

import asyncio

from .. import models as m
from ..db import SessionLocal
from ..services.core import audit, sim_state
from ..services.runtime import RUNNER, TICK_SECONDS
from . import clock


def _newest_serious_alert(db) -> int:
    row = (db.query(m.Alert.id).filter(m.Alert.audience_role == "COORDINATOR",
                                       m.Alert.severity.in_(("HIGH", "CRITICAL")))
           .order_by(m.Alert.id.desc()).first())
    return row[0] if row else 0


def step_once() -> bool:
    """Advance one tick if the clock is running. Returns True if time moved."""
    with SessionLocal() as db:
        st = sim_state(db)
        if st is None or st.paused:
            return False
        before = _newest_serious_alert(db)
        minutes = max(5, round(st.speed * TICK_SECONDS))
        clock.advance(db, minutes, None, record_audit=False)
        if RUNNER["pause_on_alert"] and _newest_serious_alert(db) > before:
            st.paused = True
            audit(db, None, "SIMULATION_AUTO_PAUSED", "simulation_state", 1,
                  after={"reason": "a new high-risk alert was raised", "sim_now": st.sim_now.isoformat()})
        db.commit()
        return True


async def run_forever() -> None:
    while True:
        await asyncio.sleep(TICK_SECONDS)
        try:
            await asyncio.to_thread(step_once)
            RUNNER["last_error"] = None
        except Exception as exc:  # keep the loop alive; the error is reported by the control endpoint
            RUNNER["last_error"] = repr(exc)
