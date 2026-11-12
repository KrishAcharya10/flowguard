# API specification (as built)

- Source of truth: Pydantic schemas in `backend/app/schemas.py`. The contract is exported to
  `contracts/openapi.json` by `scripts/export_openapi.py`; `test_exported_openapi_matches_the_running_app`
  fails if it is stale. Frontend types are generated from it (`npm run types` → `frontend/src/api/schema.d.ts`).
- Access per endpoint: `docs/API_ACCESS_MATRIX.md` (generated). Tables: `docs/DB_REFERENCE.md` (generated).
- Interactive docs while the server runs: http://127.0.0.1:8000/docs
- Example responses: `contracts/fixtures/*.json` (real responses from the G1 flow).

## Conventions

| Topic | Rule |
| --- | --- |
| Auth | `Authorization: Bearer <JWT>`; HS256, 60 min; role and active flag re-read from the DB every request |
| Errors | 401 not logged in · 403 wrong role · 404 not found **or someone else's resource** · 409 conflict (invalid transition, stale scenarios, already decided) · 422 validation · 429 login throttle |
| Time | All timestamps are UTC ISO-8601 with `Z`. The UI displays Asia/Kolkata |
| Units | hours, km, tonnes, t/h, Rs |
| GETs | Never run Monte Carlo; they read stored predictions |
| Customer responses | Separate allow-list schemas (`Customer*Out`), no costs/penalties/rates/other customers |

## Endpoints by group

| Group | Endpoints |
| --- | --- |
| Auth | `POST /api/auth/login`, `GET /api/auth/me` |
| Customer | `GET /api/customer/me/orders`, `GET /api/customer/me/shipments`, `GET /api/customer/me/shipments/{id}`, `GET /api/customer/me/alerts`, `POST /api/customer/me/alerts/{id}/acknowledge` |
| Transporter | `GET /api/transporter/me/shipments`, `POST /api/transporter/shipments/{id}/milestones` (next state only, not in the future, idempotent), `POST /api/transporter/shipments/{id}/pod` |
| Control tower | `GET /api/control-tower/overview`, `GET /api/control-tower/map-data` |
| Orders / shipments | `GET /api/orders/{id}`, `GET /api/shipments`, `GET /api/shipments/{id}`, `GET /api/shipments/{id}/events`, `GET /api/shipments/{id}/prediction?history=true`, `POST /api/shipments/{id}/recalculate` |
| Simulation | `GET /api/simulation/clock`, `POST /api/simulation/clock/advance`, `GET/POST /api/simulations/disruptions`, `POST /api/simulations/disruptions/{id}/end` |
| War Room | `POST/GET /api/shipments/{id}/scenarios`, `GET /api/interventions`, `POST /api/interventions/{id}/approve`, `POST /api/interventions/{id}/reject` |
| Alerts / audit | `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge`, `GET /api/audit-events` |
| Analytics | `GET /api/analytics/overview`, `/delay-causes`, `/routes`, `/transporters`, `/business-impact` |
| Assumptions | `GET /api/assumptions`, `PUT /api/assumptions` (bumps version, recalculates, supersedes open cases, audits) |
| Demo guide | `GET /api/demo/use-cases`, `POST /api/demo/use-cases/{code}/setup` (`mode`: start or jump; DEMO_MODE only) |
| Live operations | `GET /api/sync/state` (change stamp, all roles), `GET /api/activity`, `POST /api/simulation/clock/control`, `POST /api/orders`, `POST /api/transporter/shipments/{id}/report`, `GET /api/transporter/me/history`, `GET /api/customer/me/history` |
| Gate slots | `GET /api/gate/overview`, `/summary`, `/bookings`; `POST /api/gate/bookings`, `/{id}/reschedule`, `/{id}/cancel`, `/{id}/complete`; `PUT /api/gate/slots/{id}`; driver: `GET /api/transporter/me/gate`, `POST /api/transporter/gate/bookings/{id}/check-in` |
| Documents | `GET /api/documents/overview`, `GET /api/orders/{id}/documents`, `POST /api/orders/{id}/invoice` (raw file body), `POST /api/documents/{id}/verify`, `GET /api/documents/{id}/download`, driver `POST /api/transporter/shipments/{id}/pod-document`, customer `GET /api/customer/me/documents` |
| Chat | `POST /api/customer/me/chat` (rule-based, read-only) |
| Reference / admin | `GET /api/reference-data`, `POST /api/admin/reset` (DEMO_MODE only), `GET /health` |

## Intervention lifecycle

```
AWAITING_APPROVAL ──approve──▶ APPROVED ──(same transaction)──▶ APPLIED ──all lots at gate──▶ COMPLETED
        │──reject──▶ REJECTED
        └──new case / assumptions change / stale on approve──▶ SUPERSEDED
```
Each case snapshots `shipment.state_version`, `assumptions_version`, `clock_version`. Approve returns
**409** and marks the case SUPERSEDED if any differs. Approve/reject are idempotent. Approving a
non-recommended or infeasible option requires `override_reason` (≥ 5 chars) and writes
`CONSTRAINT OVERRIDE`. Applying is one DB transaction: route change or split, event, new prediction,
customer + coordinator alerts, audit.

`state_version` bumps on material events only (milestone, disruption start/end touching the shipment,
telemetry outage, applied intervention); never on clock ticks. `clock_version` bumps on every advance.
