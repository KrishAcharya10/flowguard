# UI specification (as built)

React 18 + Vite + TypeScript + Tailwind + Recharts + Leaflet. Code: `frontend/src/`.
Seven views (spec maximum). Alerts are a drawer, not a page.

| # | View | Route | Role | Key content |
| --- | --- | --- | --- | --- |
| 1 | Login / role select | `/login` | all | Role cards fill the username; manual password entry |
| 2 | Control Tower | `/tower` | coordinator | 7 KPI cards (buckets sum to active total), map, shipment table sorted by risk with filters (status, route, transporter, customer), simulation controls (inject disruption, advance clock, end disruption, reset), alerts drawer |
| 3 | Shipment Detail | `/shipments/:id` | coordinator | Milestone bar, ETA intelligence (promise, P50, P10–P90, P(late), P(stock-out), risk index, data confidence), reason chips as mean contributions, "P50 moved +x h since … : <trigger>", prediction history chart, stock cover, event log |
| 4 | War Room | `/shipments/:id/war-room` | coordinator | Recommendation banner with explanation, plain comparison table (Continue / Reroute / Split), ineligible options greyed with reason, violations, approve / override with reason / reject, stability card with 16 cases |
| 5 | Customer Portal | `/customer` | customer | Delivery updates (alerts), per order: original promise beside "Updated expected delivery", likely range, risk level, milestones, last reported position on a map, action note after approval |
| 6 | Transporter Portal | `/driver` | transporter | Assigned shipments, one large "Confirm: <next milestone>" button, proof of delivery (recipient name), route-change instruction |
| + | Demo guide | `/demo` | coordinator | 8 use cases (story, what it proves, windows, steps with links), Start / Jump setup, floating presenter panel on every coordinator page |
| 7 | Analytics | `/analytics` | coordinator | Tabs: Performance (O5), Business impact (Panel A + B, labelled MODELLED), Intervention history, Assumptions (editable), Audit trail, Responsible AI |

## Rules applied

- Every KPI and chart reads the API; no decorative data.
- Loading, empty, error (with retry) states on every data view (`components/ui.tsx → State`).
- Never colour alone: every status badge has an icon and a text label (✓ Low, ▲ Medium, ● High, ⚠ Stale).
- Map: Leaflet vector layers only (`circleMarker`, `divIcon`); offline labelled grid by default; optional
  OSM tiles removed after three consecutive `tileerror` events; caption "Illustrative routes. Positions are
  simulated."; stale vehicles drawn dashed/faded with "last REPORTED position".
- Customer wording: "Original promise" and "Updated expected delivery", never "new commitment". Before
  approval: "evaluating an alternate route"; after the transactional apply: "Rerouting has been initiated".
- Times shown in Asia/Kolkata; ETAs rounded to 5 min; probabilities as whole percent.
- Accessibility: visible keyboard focus ring, labelled form controls, `role=alert/status` for messages,
  `aria-label` on the map and dialogs, contrast-checked navy/grey/white palette.
- No CDN: fonts are system fonts; icons are Unicode; all JS/CSS is bundled. FastAPI serves `frontend/dist`
  with SPA fallback on the same origin.
- Tokens in `sessionStorage` (one login per tab).
