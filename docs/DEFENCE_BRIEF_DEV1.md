# Defence brief — Dev1 (backend, data, security)

## Your modules
`backend/app/models.py`, `db.py`, `security.py`, `api/`, `schemas.py`, `services/shipments.py`,
`services/warroom.py` (lifecycle part), `services/analytics.py`, `seed/`.

## Key ideas in words
- **Access**: three roles. The token only says who you are; your role and active flag are read fresh from the
  database each request. Wrong role: 403. Another customer's or driver's record: 404.
- **Privacy**: customers get their own response shapes that simply have no cost, penalty, rate, risk-weight or
  transporter fields. A test walks every key of every customer response looking for those words.
- **Integrity**: milestones only move forward, one step; the promise date is never changed; predictions and
  audit rows are only inserted, never edited.
- **Approval freshness**: case stores three versions (shipment, assumptions, clock); mismatch → 409.
- **On-time KPI**: an order is on time if **every** lot reached the customer gate by the promise (+ grace).
  Orders still moving are excluded; predicted on-time is shown separately.
- **Delay attribution**: realised delay = arrival − planned arrival (never negative); split across observed
  causes by overlap; the rows never overlap in time and add up to the realised delay (tolerance 0.001 h).

## Numbers to know
43 API endpoints; 126 backend tests; 18 tables; 14 live + 160 historical shipments; overview with 80 live
shipments ≈ 150–210 ms; login throttle 5 failures per minute per username + IP.

## Three hard questions
1. **"Your token is in sessionStorage — isn't that an XSS risk?"** Yes. We chose it so each demo tab can be a
   different role. React escapes output and we render no user HTML, but a pilot would use HttpOnly SameSite
   cookies plus CSRF protection. It is in `KNOWN_LIMITATIONS.md`.
2. **"What if two coordinators approve at once?"** It cannot be applied twice. SQLite allows one writer at a
   time. If the second request starts after the first commits, it sees the case APPLIED: same option →
   idempotent success, different option → 409. If both start at the same instant, the second one's write is
   refused by SQLite and its transaction is rolled back (the user sees an error and retries). A pilot on
   PostgreSQL would lock the case row (`SELECT … FOR UPDATE`) to return a clean 409 every time.
3. **"How do you know KPIs are computed correctly?"** Tests recompute on-time and average delay independently
   from the raw rows, check that buckets sum to the active total, and that delay events sum to realised delay
   for every one of 160+ arrivals.
