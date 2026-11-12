# CLAUDE.md — FlowGuard

## Identity
FlowGuard ("Predict. Simulate. Deliver.") is a decision-support Order-to-Delivery Control Tower for the
**fictional** Plant X. LYB Mumbai Hackathon 2026, Round 2, Problem Statement 3.
Authority: the official PDF (`docs/source/`) for requirements; `docs/source/FLOWGUARD_FINAL_MASTER_PROMPT_V3_2.md`
for engineering. On conflict with the PDF: stop and report.

## Official requirements (never cut)
- O1 Separate logins: customer, logistics coordinator, transporter/driver.
- O2 Track orders and shipments on a map with status milestones.
- O3 Predict ETA and delay risk per shipment and show the reason.
- O4 Alert customer and coordinator on delay risk with a suggested action (reroute or split).
- O5 Dashboard: on-time performance and delay causes by route and transporter.

## Scope classes
O = O1–O5. D1 engine, D2 War Room, D3 stock cover, D4 assumptions + stability (built).
E = escalation, auto clock, driver hazards (not built); custom disruption durations built. X = bonus (POD status only).

## Status
All phases built. See `PROGRESS.md` (state) and `docs/FINAL_AUDIT.md` (evidence).

## Commands
- Backend tests: `cd backend && .venv\Scripts\python -m pytest -q` (217)
- Start (builds the site first): `start-flowguard.cmd`. The server shows the BUILT site and does not auto-reload.
- Check the running site: `cd frontend && npx playwright test -c playwright.live.config.ts`
- Never let a script reset against the live server's document folder: set `FLOWGUARD_DOC_DIR` to a temp folder
- Demo guide use cases: `backend/app/services/demo.py` (steps + jump setup); UI `frontend/src/pages/DemoGuide.tsx`
- Re-record FLOW.md numbers: `backend\.venv\Scripts\python scripts\record_flow.py`
- Hand-check: `backend\.venv\Scripts\python scripts\phase0_handcheck.py`
- Run: `cd backend && .venv\Scripts\python -m uvicorn app.main:app --port 8000 --workers 1`
- Reset data: `cd backend && .venv\Scripts\python -m app.seed.reset`
- Frontend: `cd frontend && npm run build` · dev `npm run dev` · E2E `npx playwright test`
- After any schema change: `scripts/export_openapi.py`, then `npm run types` in `frontend/`
- Regenerate reference docs: `scripts/gen_reference_docs.py`

## Ownership
Dev1 backend/data/security (integration owner) · Dev2 frontend/UX · Dev3 engine/QA/demo.

## Hard rules
- No `datetime.now()`/`time.time()` in business logic; time comes from `simulation_state` (security.py excepted).
- Never Python `hash()`; seeds use `zlib.crc32`. `seed_pred` and `seed_truth` stay separate.
- `engine/` imports NumPy only; `engine/` and `services/` never import `simulator/` (tested).
- Exactly one ETA function: `engine/eta.py::simulate_arrival`.
- Pydantic schemas are the API source of truth; `contracts/openapi.json` must match (tested).
- Customer endpoints use `Customer*` allow-list schemas; never add costs, penalties, rates, weights.
- Canonical states: `PLANNED > LOADING > AT_PLANT_GATE > IN_TRANSIT > ARRIVED_AT_CUSTOMER_GATE > DELIVERED`;
  `SPLIT_PARENT` is a disposition. Never `AT_GATE`/`ARRIVED`.
- `promised_at` is immutable. Customer wording: "Updated expected delivery", never "new commitment".
- Every modelled money figure is labelled MODELLED. Rs, fictional.
- Infeasible options are never recommended; overrides need a reason and a `CONSTRAINT OVERRIDE` audit row.
- GET endpoints never run Monte Carlo.
- Golden target ranges (`docs/GOLDEN_SCENARIO.md`) are never edited; only distribution parameters, logged in
  `docs/GOLDEN_BASELINE.md`.
- Never report a test as passed without running it. Update `docs/AI_DISCLOSURE.md` for any new AI use.
- No paid API, secret or CDN in the demo path. The ONLY external call is the optional OpenStreetMap map tiles (no key; on by default when online, attribution shown). If they cannot load, the map switches to the local "Illustrative logistics network" automatically, so the demo works fully offline.

## Stop and ask if
A paid service or secret is needed; a destructive operation on existing files; a frozen contract must change;
an official requirement is at risk; a major architecture decision must change.
