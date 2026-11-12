# Phase 2 walkthrough — predictions, alerts, War Room, approval, analytics

## Dev3 area (decision logic)

- **Stored predictions** (`services/predictions.py`): recalculated after a milestone, disruption start/end,
  approved intervention, assumptions change or clock advance. Pages only read them, so they are fast.
- **Reasons** ("reason chips"): how many hours each cause adds **on average** versus an undisturbed trip.
  A final "travel variability" item makes them add up exactly.
- **"P50 moved +5.4 h because flooding event DSR-001"**: because each shipment always uses the same random
  numbers, the change between two predictions is caused by what changed, not by luck.
- **War Room** (`engine/warroom.py`, `services/warroom.py`): three options on the same random numbers.
  Cost = extra freight + penalty × expected late hours + stock-out rate × expected stock-out hours. Options
  that break a hard rule are never recommended. If nothing beats Continue by a meaningful margin, the answer is
  "No justified intervention". If every option breaks a rule, the answer is "No feasible option – escalate".
- **Stability**: the comparison is repeated 16 times with costs and flood duration 25% higher or lower.

## Dev1 area (workflow and data integrity)

- **Approval safety**: each decision case remembers the shipment version, assumptions version and clock
  version. If any changed before approval, the server answers 409 "out of date, re-run".
- **One transaction**: approving changes the route (or creates two child lots), writes an event, recalculates,
  notifies customer and coordinator, and writes the audit entry together, or none of it happens.
- **Split**: the parent becomes `SPLIT_PARENT` (not delivered, excluded from KPIs); two child lots whose
  tonnes add up exactly; the urgent lot gets a different fictional driver.
- **Alerts** (`services/alerts.py`): coordinators get the specific suggestion and numbers; customers get a
  plain message with no costs. Duplicate alerts are blocked by a unique key.
- **Analytics** (`services/analytics.py`): on-time is judged per **order** at **customer-gate arrival**
  (not proof of delivery). Delay hours per cause add up exactly to each shipment's real delay.

## Check yourself

1. Why is stock-out cost "rate × expected hours" and not "fixed cost × probability"?
2. What three things make an approval "out of date"?
3. Why is a split parent excluded from on-time KPIs?
