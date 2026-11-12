# Phase 0 walkthrough — design, contracts and the hand-check

**Read by:** all three developers. Time: 15 minutes.

## What happened

Before any feature was built, we proved the three demo stories (G1, G2, G3) can all be true with one set of
numbers. If they could not, the demo would contradict itself.

## What was produced

| File | Plain-language meaning |
| --- | --- |
| `docs/source/requirements.md` | The official PDF text, copied with page numbers. This is the rulebook |
| `docs/GOLDEN_SCENARIO.md` | The three demo stories and the ranges their numbers must fall in. Written **before** tuning |
| `backend/app/engine/contracts.py` | The exact shape of what goes into and comes out of the maths engine |
| `backend/app/seed/network.py` | The fictional map: Plant X, 4 routes, 2 bypasses, 3 customers, 3 transporters |
| `scripts/phase0_handcheck.py` | Builds G1–G3 by hand (no database) and checks all 29 targets |

## The one tuning change

The first run failed one check: with the Dhule Bypass at 44 km/h, Reroute's chance of a stock-out was 1.8%,
below the target 2–8%. We did **not** change the target. We slowed the bypass to 42 km/h (a distribution
parameter, which the rules allow). All 29 checks then passed: `RESULT: ALL TARGETS COMPATIBLE - GO`.
Logged in `docs/GOLDEN_BASELINE.md`.

## Why G1, G2, G3 can coexist

- G1 and G2 have the **same flood**. The difference is the customer: G1's customer has 12.5 h of stock and a
  Rs 20,000/h penalty; G2's has 80 h of stock and Rs 2,500/h. Same lateness, very different cost.
- G3 is G1 with stricter rules (stock-out ≤ 1%, freight ≤ Rs 20,000), so every option breaks a rule.

## Process note (be ready to say this)

The master prompt asked us to stop after Phase 0 for human approval. The user instructed the AI to
"start now and complete", so the build continued without a separate approval stop. The Phase 0 outputs are
still here so the team can review them.

## Check yourself

1. Why must target ranges never be edited to make tests pass?
2. What single parameter was tuned, and why is that allowed?
3. Why does G2 recommend Continue even though it is almost certainly late?
