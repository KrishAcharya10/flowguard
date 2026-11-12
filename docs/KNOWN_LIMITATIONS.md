# Known limitations

Honest list for judges and for a pilot plan. None of these affects the official requirements O1–O5.

## Modelling

| Limitation | Effect | What a pilot would do |
| --- | --- | --- |
| All distributions are assumptions, not fitted to data | Probabilities show uncertainty **under the assumptions**, not proven accuracy | Shadow mode: predict without acting, compare with actual arrivals, recalibrate σ and durations |
| Closure blocks **entry** only; a vehicle already inside a segment is unaffected | Slight optimism for a truck already on a flooded segment | Segment-level geofencing and finer segments |
| Slowdown applies by entry time, no piecewise integration | A slowdown that starts mid-segment is ignored for that segment | Split long segments |
| Single-shipment decisions; no fleet optimisation | Two shipments may both be told to use the same second vehicle | Fleet-level capacity check |
| The second vehicle is assumed available after a fixed 1.5 h | Real spot-hire availability varies | Transporter capacity feed |
| Delay attribution splits realised delay by overlap time; unexplained delay → ROUTE_CONGESTION | Approximate cause analytics | Driver-reported reasons and telematics events |
| Monte Carlo N = 500 | Probabilities carry up to ~2.2 percentage points of sampling error (shown in the UI) | Raise N (the engine is vectorised) |

## Data

- All data is fictional and seeded deterministically. Customer stock data is fictional; a real deployment needs
  customer consent to share coarse stock-cover data.
- Positions are simulated; routes are illustrative straight-line polylines on a labelled grid.

## Security and operations

| Limitation | Note |
| --- | --- |
| JWT in `sessionStorage` | Exposed to any XSS in the page. Chosen so each demo tab can hold a different role. A pilot would use HttpOnly, SameSite cookies and CSRF protection |
| JWT secret is random per process in demo mode | All tokens become invalid on server restart (log in again). Outside demo mode the server refuses to start without `FLOWGUARD_JWT_SECRET` |
| Login throttle is in memory | Resets on restart; per process only |
| SQLite, one Uvicorn worker | Correct for a demo; a pilot would use PostgreSQL and a job queue for recomputation |
| Token expiry and the login throttle use the wall clock | Documented exception: security plumbing, not business logic |
| No HTTPS in the local demo | Put behind a TLS proxy for any real use |
| Demo password is shared by all seeded accounts | Fictional accounts only, seeded only when `DEMO_MODE=true` |

## Live operations and bonus features

| Limitation | Note |
| --- | --- |
| Live updates use polling (every 2.5 s) | Simple and reliable; a pilot would use server-sent events or WebSockets |
| The auto-running clock stores one prediction set per tick | Fine for a demo; a pilot would store a prediction only when it materially changes |
| Running the clock invalidates open War Room cases | By design (approvals need a frozen situation); the UI blocks approval while the clock runs |
| Gate slot rules run under one in-process lock | Correct for one server process; several servers would need a database-level reservation (PostgreSQL row locks) |
| Slots are a fixed hourly grid, 5 days around the simulated today | No variable slot lengths, no per-lane capacity |
| The gate and documents use simulated time, shown in IST | Never the real clock; a real deployment would use real time |
| The chatbot is rule-based (keywords → intent) | It will say "I am not sure" to unusual wording; it never guesses. No language model is used |
| Documents are stored on local disk | Private and access-checked, but no antivirus scan, encryption at rest or off-site backup |
| A proof-of-delivery file is optional (driver may record delivery without one) | The coordinator sees "Delivered · no document" |
| POD "verification" is a human confirmation, not automatic content checking | The system cannot read the signature |

## Scope not built

- Auto-advancing clock, alert escalation timers, driver-reported hazards (scope class E). Custom disruption
  durations are available (Control Tower → Custom duration); custom multipliers only through the API.
- Performance was tested to 80 live shipments (≈ 150–210 ms for the Control Tower overview); not load-tested beyond.
