# Defence brief — Dev3 (engine, QA, demo)

## Your modules
`backend/app/engine/`, `services/mapping.py`, `services/predictions.py`, `services/alerts.py`,
`simulator/`, `scripts/phase0_handcheck.py`, `tests/`, `docs/GOLDEN_*`, `docs/DEMO_RUNBOOK.md`.

## Key formulas in words
- **Arrival** = remaining loading + gate queue + Σ(segment distance ÷ speed × trip factor × segment factor ×
  slowdown) + closure waits + repair wait. 500 samples.
- **Factors** have average 1 (`exp(σZ − σ²/2)`), so they widen the range without shifting the mean.
- **P(late)** = share of samples after the promise. **P50** = median. Shown rounded: 5 min, whole percent.
- **Stock-out**: stock runs out at S = now + inventory ÷ consumption; usable arrival = arrival + unloading;
  lots refill in arrival order.
- **Risk index** = 100 × (0.6 P(late) + 0.4 P(stock-out)), with floors.
- **Option total** = extra freight + SLA rate × expected late hours + stock-out rate × expected stock-out hours.
- **Recommendation** = cheapest option that breaks no hard rule, unless it saves less than
  max(2% of Continue, Rs 2,000), then Continue.

## G1 numbers to know (seeded demo)
Before flood: P(late) 0.6%, Low. After flood, Continue: P(late) 100%, P(stock-out) 95%, P50 2.9 h after the
promise, total Rs 1,76,660. Reroute: P(late) 20%, P(stock-out) 4%, freight Rs 8,131, total Rs 12,095.
Split: P(stock-out) 76%, freight Rs 40,626. Recommendation REROUTE, STABLE 16/16.

## Three hard questions
1. **"Isn't a 95% probability over-confident for made-up inputs?"** It is 95% *under our stated assumptions*:
   the flood lasts 7–12 h and the customer's stock lasts 12.5 h. We never claim empirical accuracy; the UI
   says so. A pilot would calibrate in shadow mode.
2. **"Why not train an ML model?"** There is no real history; training on data we generated ourselves would
   just learn our own assumptions back. A transparent simulation is honest and explainable.
3. **"How do you know options are compared fairly?"** Common random numbers: every option uses the same trip
   factor, the same flood duration and the same segment factors on shared roads, so differences come from the
   option itself. A test checks the correlation between Continue and Reroute samples is above 0.9.
