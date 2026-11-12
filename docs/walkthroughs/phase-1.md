# Phase 1 walkthrough — foundation: database, seed, logins, engine, simulator

## Dev1 area (backend and data)

- **Database** (`backend/app/models.py`, reference in `docs/DB_REFERENCE.md`): 18 tables. The important ones:
  `orders` (holds the **promise**, which never changes), `shipments` (state, version number, last reported
  position), `predictions` (one row per calculation, never edited), `audit_events` (never edited).
- **SQLite settings** (`db.py`): WAL mode so reads don't block writes; foreign keys switched on for every
  connection; 5-second busy timeout.
- **Seed** (`seed/reset.py`): rebuilds everything from fixed numbers. Simulated time starts at
  16 Nov 2026 06:00 IST, so every demo starts identically. 14 live shipments and 160 historical ones with three
  planted patterns for the dashboard to find.
- **Logins** (`security.py`): passwords hashed with Argon2; a signed token lasting 60 minutes. On **every**
  request we re-read the user from the database, so a disabled user is locked out immediately.
  Wrong role → 403. Someone else's shipment → 404, so nobody learns that it exists.
- **Milestones** (`services/shipments.py`): a shipment can only move to the next state. A driver can only move
  their own shipment, not into the future; pressing twice does nothing the second time.

## Dev3 area (engine and simulator)

- **The engine** (`engine/eta.py`) simulates the remaining trip 500 times. Each run draws: how long loading
  and the gate queue take, a "how is today going" factor for the whole route, a small factor for each road
  segment, and how long any closure lasts. The 500 arrival times give the median (P50), the range
  (P10–P90) and the chance of arriving after the promise.
- **Stock** (`engine/stock.py`): when the customer's stock runs out, and how many hours they would be without
  material. With two lots, whichever arrives first refills the stock first.
- **Risk** (`engine/risk.py`): a 0–100 score = 60% lateness + 40% stock-out chance, with floors so a 50% chance
  of lateness can never show as Low.
- **Simulator** (`simulator/`): decides what "really" happens, using different random seeds from the
  predictor. It writes only what a real system would see: milestones and a position every 5 simulated
  minutes. The predictor never imports it.

## Check yourself

1. Why return 404 rather than 403 for another customer's shipment?
2. What does the "route factor" represent, and why is it shared by all segments?
3. Why are prediction seeds and truth seeds different?
