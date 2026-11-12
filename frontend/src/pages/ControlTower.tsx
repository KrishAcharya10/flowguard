// Coordinator control tower: simulation control, headline KPIs, live map, alerts and disruptions,
// active shipments table, live activity feed, interventions. Every number comes from the backend.
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, refreshAll, useApi, type Alert, type CaseOut, type ControlTower as CT, type Disruption, type GateSummary, type MapData, type ReferenceData } from '../api/client'
import ActivityFeed from '../components/ActivityFeed'
import Icon from '../components/Icons'
import MapView from '../components/MapView'
import NewOrderDialog from '../components/NewOrderDialog'
import ShipmentPanel from '../components/ShipmentPanel'
import SimControl from '../components/SimControl'
import { BucketBadge, Card, ConfidenceBadge, Notice, RiskBadge, State } from '../components/ui'
import { fmtEta, fmtTime, pct } from '../lib/format'

function Stat({ icon, label, value, sub, tone = 'navy' }: { icon: string; label: string; value: ReactNode; sub?: ReactNode; tone?: 'navy' | 'green' | 'amber' | 'red' | 'blue' }) {
  const t = { navy: 'bg-navy-100 text-navy-800', green: 'bg-emerald-100 text-emerald-800', amber: 'bg-amber-100 text-amber-800', red: 'bg-red-100 text-red-800', blue: 'bg-sky-100 text-sky-800' }[tone]
  return (
    <div className="card p-3.5 flex gap-3 items-start">
      <span className={`h-10 w-10 shrink-0 rounded-xl flex items-center justify-center ${t}`}><Icon name={icon} size={20} /></span>
      <div className="min-w-0">
        <div className="label !text-[11px]">{label}</div>
        <div className="text-2xl font-bold text-navy-900 leading-tight">{value}</div>
        {sub && <div className="text-[11px] text-slate-500 leading-snug">{sub}</div>}
      </div>
    </div>
  )
}

function Injector({ refData, shipments }: { refData: ReferenceData; shipments: CT['shipments'] }) {
  const [preset, setPreset] = useState('FLOOD_R1')
  const [shipment, setShipment] = useState('')
  const [custom, setCustom] = useState(false)
  const [dur, setDur] = useState<[string, string, string]>(['', '', ''])
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [busy, setBusy] = useState(false)
  const p = refData.presets.find((x) => x.code === preset)
  const candidates = shipments.filter((s) => s.disposition === 'ACTIVE' && p?.requires_state.includes(s.state))
  const inject = async () => {
    setBusy(true)
    setMsg(null)
    try {
      const durBody = custom ? { dur_min_h: Number(dur[0]), dur_mode_h: Number(dur[1]), dur_max_h: Number(dur[2]) } : {}
      await api('/api/simulations/disruptions', { method: 'POST', body: { preset, shipment_id: p?.needs_shipment ? shipment || null : null, ...durBody } })
      setMsg({ kind: 'ok', text: 'Disruption injected. Predictions recalculated.' })
      refreshAll()
    } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div>
      <div className="label mb-1">Disruption injector (simulated event)</div>
      <label className="sr-only" htmlFor="preset">Disruption preset</label>
      <select id="preset" className="input" value={preset} onChange={(e) => { setPreset(e.target.value); setShipment(''); setCustom(false) }}>
        {refData.presets.map((x) => <option key={x.code} value={x.code}>{x.label}</option>)}
      </select>
      {p?.needs_shipment && (
        <>
          <label className="sr-only" htmlFor="pship">Shipment</label>
          <select id="pship" className="input mt-2" value={shipment} onChange={(e) => setShipment(e.target.value)}>
            <option value="">Choose a shipment ({p.requires_state.join(' / ').toLowerCase().replace(/_/g, ' ')})</option>
            {candidates.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
          </select>
        </>
      )}
      <div className="text-xs text-slate-500 mt-1">Duration (min / most likely / max): {p?.duration.join(' / ')} h{p?.multiplier ? ` · factor x${p.multiplier}` : ''}</div>
      <label className="text-xs flex items-center gap-1 mt-1"><input type="checkbox" checked={custom} onChange={(e) => { setCustom(e.target.checked); if (p) setDur([String(p.duration[0]), String(p.duration[1]), String(p.duration[2])]) }} /> Custom duration</label>
      {custom && (
        <div className="grid grid-cols-3 gap-1 mt-1">
          {(['Min h', 'Most likely h', 'Max h'] as const).map((lbl, i) => (
            <label key={lbl} className="text-[11px] text-slate-600">{lbl}
              <input className="input" inputMode="decimal" value={dur[i]} onChange={(e) => { const d = [...dur] as [string, string, string]; d[i] = e.target.value; setDur(d) }} />
            </label>
          ))}
        </div>
      )}
      <button className="btn-danger mt-2" onClick={inject} disabled={busy || (p?.needs_shipment && !shipment)}>Inject disruption</button>
      {msg && <div className="mt-2"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </div>
  )
}

function Disruptions() {
  const dis = useApi<Disruption[]>('/api/simulations/disruptions')
  const [err, setErr] = useState('')
  const end = async (id: string) => {
    setErr('')
    try { await api(`/api/simulations/disruptions/${id}/end`, { method: 'POST' }); refreshAll() } catch (e) { setErr((e as Error).message) }
  }
  const active = dis.data?.filter((d) => d.status === 'ACTIVE') ?? []
  return (
    <div>
      <div className="label mb-1">Active disruptions ({active.length})</div>
      <State loading={dis.loading && !dis.data} error={dis.error} empty={!!dis.data && active.length === 0} emptyText="None right now." onRetry={dis.reload} />
      {err && <Notice kind="error">{err}</Notice>}
      <ul className="space-y-1">
        {active.map((d) => (
          <li key={d.id} className="text-xs flex items-center justify-between gap-2 rounded border border-amber-300 bg-amber-50 px-2 py-1">
            <span><strong>{d.label}</strong> · {d.id}{d.shipment_id ? ` · ${d.shipment_id}` : ''} · since {fmtTime(d.start_at)}</span>
            <button className="btn-secondary !py-0.5 !px-2" onClick={() => end(d.id)}>End</button>
          </li>
        ))}
      </ul>
    </div>
  )
}

function OpenAlerts() {
  const nav = useNavigate()
  const al = useApi<Alert[]>('/api/alerts?only_open=true')
  const ack = async (id: number) => { await api(`/api/alerts/${id}/acknowledge`, { method: 'POST' }); refreshAll() }
  const rows = (al.data ?? []).slice(0, 4)
  return (
    <div>
      <State loading={al.loading && !al.data} error={al.error} empty={!!al.data && al.data.length === 0} emptyText="No open alerts. Everything is on plan." onRetry={al.reload} />
      <ul className="space-y-2">
        {rows.map((a) => (
          <li key={a.id} className="rounded-lg border border-slate-200 p-2.5">
            <div className="flex items-center justify-between gap-2"><RiskBadge level={a.severity} prefix="" /><span className="text-[11px] text-slate-500">{fmtTime(a.created_sim_at)}</span></div>
            <div className="text-sm font-semibold mt-1">{a.title}</div>
            {a.suggested_action && <div className="text-xs text-slate-700 mt-0.5 line-clamp-2">{a.suggested_action.replace(/^Suggested action: /, 'Suggested: ')}</div>}
            <div className="flex gap-1.5 mt-1.5">
              {a.shipment_id && <button className="btn-primary !py-1 !px-2 !text-xs" onClick={() => nav(`/shipments/${a.shipment_id}/war-room`)}>War Room</button>}
              <button className="btn-secondary !py-1 !px-2 !text-xs" onClick={() => ack(a.id)}>Acknowledge</button>
            </div>
          </li>
        ))}
      </ul>
      {(al.data?.length ?? 0) > 4 && <p className="text-xs text-slate-500 mt-1">+{(al.data?.length ?? 0) - 4} more in the Alerts drawer.</p>}
    </div>
  )
}

function GateCard() {
  const nav = useNavigate()
  const g = useApi<GateSummary>('/api/gate/summary')
  const d = g.data
  const pct = d && d.capacity ? Math.min(100, Math.round((100 * d.booked) / d.capacity)) : 0
  const t = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false })
  return (
    <Card title={`Gate slots today${d ? ` · ${d.day_label}` : ''}`} right={<button className="btn-secondary !py-1" onClick={() => nav('/gate')}><Icon name="gate" size={14} />Open schedule</button>}>
      <State loading={g.loading && !d} error={g.error} onRetry={g.reload} />
      {d && (
        <div className="grid md:grid-cols-3 gap-4 items-center">
          <div>
            <div className="flex items-end justify-between"><span className="text-3xl font-bold text-navy-900">{d.booked}<span className="text-base font-semibold text-slate-500"> / {d.capacity}</span></span><span className="text-xs text-slate-500">places booked</span></div>
            <div className="h-3 rounded-full bg-slate-200 mt-2 overflow-hidden"><div className={`h-3 ${pct >= 90 ? 'bg-amber-500' : 'bg-sky-600'}`} style={{ width: `${pct}%` }} /></div>
            <div className="text-xs text-slate-500 mt-1">{d.full_slots} full slot(s) · {d.unavailable_slots} unavailable</div>
          </div>
          <ul className="md:col-span-2 grid sm:grid-cols-2 gap-2">
            {d.upcoming.length === 0 && <li className="text-sm text-slate-500">No upcoming bookings.</li>}
            {d.upcoming.map((b) => (
              <li key={b.id} className="rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs flex items-center gap-2"><span className="font-bold tabular-nums">{t(b.slot_start)}</span><span className="font-semibold">{b.shipment_id}</span><span className="text-slate-500 truncate">{b.vehicle_label.replace(' (fictional)', '')}</span><span className={`ml-auto font-bold ${b.status === 'CHECKED_IN' ? 'text-amber-700' : 'text-sky-700'}`}>{b.status.replace('_', ' ')}</span></li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

function Interventions() {
  const nav = useNavigate()
  const iv = useApi<CaseOut[]>('/api/interventions')
  const rows = (iv.data ?? []).slice(0, 6)
  const pending = (iv.data ?? []).filter((c) => c.status === 'AWAITING_APPROVAL' && !c.is_stale).length
  const chosen = (c: CaseOut) => c.scenarios.find((s) => s.id === c.selected_scenario_id)?.code
  return (
    <Card title="Interventions and approvals" right={<span className={`text-xs font-semibold rounded-full px-2 py-0.5 ${pending ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'}`}>{pending} awaiting approval</span>}>
      <State loading={iv.loading && !iv.data} error={iv.error} empty={!!iv.data && iv.data.length === 0} emptyText="No decision cases yet. Open a shipment's War Room to compare options." onRetry={iv.reload} />
      <ul className="divide-y divide-slate-100">
        {rows.map((c) => (
          <li key={c.id} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-semibold">#{c.id}</span>
            <Link className="underline text-navy-700" to={`/shipments/${c.shipment_id}/war-room`}>{c.shipment_id}</Link>
            <span className="text-xs text-slate-600">recommended: {c.recommendation.code.replace(/_/g, ' ').toLowerCase()}</span>
            {chosen(c) && <span className="text-xs">chosen: <strong>{chosen(c)}</strong>{c.is_override ? ' (override)' : ''}</span>}
            <span className={`ml-auto text-[11px] font-bold rounded px-1.5 py-0.5 ${c.status === 'APPLIED' || c.status === 'COMPLETED' ? 'bg-emerald-100 text-emerald-900' : c.status === 'AWAITING_APPROVAL' ? 'bg-amber-100 text-amber-900' : 'bg-slate-100 text-slate-700'}`}>{c.status.replace('_', ' ')}</span>
            {c.status === 'AWAITING_APPROVAL' && !c.is_stale && <button className="btn-primary !py-0.5 !px-2 !text-xs" onClick={() => nav(`/shipments/${c.shipment_id}/war-room`)}>Review</button>}
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500 mt-2">Full decision history and the audit trail: <Link className="underline" to="/analytics">Analytics</Link>.</p>
    </Card>
  )
}

export default function ControlTower() {
  const nav = useNavigate()
  const ct = useApi<CT>('/api/control-tower/overview')
  const map = useApi<MapData>('/api/control-tower/map-data')
  const ref = useApi<ReferenceData>('/api/reference-data')
  const [f, setF] = useState({ bucket: '', route: '', transporter: '', customer: '' })
  const [selected, setSelected] = useState<string | null>(null)
  const [newOrder, setNewOrder] = useState(false)

  const rows = useMemo(() => (ct.data?.shipments ?? []).filter((s) =>
    (!f.bucket || s.bucket === f.bucket) && (!f.route || s.route_id === f.route) &&
    (!f.transporter || s.transporter_id === f.transporter) && (!f.customer || s.customer_id === f.customer))
    .sort((a, b) => (b.prediction?.risk_index ?? -1) - (a.prediction?.risk_index ?? -1) || (a.priority === 'HIGH' ? -1 : 1)), [ct.data, f])
  const visible = useMemo(() => new Set(rows.map((r) => r.id)), [rows])
  const mapRoutes = useMemo(() => (map.data?.routes ?? []).filter((r) => !f.route || r.id === f.route || r.alternative_of === f.route)
    .map((r) => ({ id: r.id, name: r.name, alternative: !!r.alternative_of, points: r.points })), [map.data, f.route])
  const mapVehicles = useMemo(() => (map.data?.vehicles ?? []).filter((v) => visible.has(v.shipment_id))
    .map((v) => ({ id: v.shipment_id, lat: v.lat, lon: v.lon, bucket: v.bucket, reported_at: v.reported_at, age_min: v.age_min, confidence: v.data_confidence })), [map.data, visible])

  if (!ct.data) return <State loading={ct.loading} error={ct.error} onRetry={ct.reload} />
  const k = ct.data.kpis
  const b = k.buckets
  const sel = (key: keyof typeof f, label: string, opts: { id: string; name: string }[]) => (
    <label className="text-xs text-slate-600">{label}
      <select className="input mt-0.5" value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })}>
        <option value="">All</option>
        {opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </label>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <h1 className="text-2xl font-bold text-navy-900">Control Tower</h1>
          <p className="text-sm text-slate-600">Every order and shipment from Plant X to the customer's gate, with predicted delays and what to do about them.</p>
        </div>
        <button className="btn-primary ml-auto !px-4 !py-2" onClick={() => setNewOrder(true)} disabled={!ref.data}><Icon name="plus" size={16} />New order</button>
      </div>

      <SimControl demoMode={ref.data?.demo_mode ?? true} />

      <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        <Stat icon="box" label="Active orders" value={k.active_orders} sub={`${k.active_shipments} shipments in progress`} />
        <Stat icon="truck" label="Active shipments" value={k.active_shipments} sub={`${b.ARRIVED_PENDING_POD} arrived, POD pending`} tone="blue" />
        <Stat icon="check" label="On-time deliveries" value={k.on_time_pct == null ? 'n/a' : `${k.on_time_pct}%`} sub={`${k.orders_on_time} of ${k.orders_completed} orders, last ${k.window_days} days`} tone="green" />
        <Stat icon="clock" label="Delayed shipments" value={k.delayed_shipments} sub="late now or predicted late" tone="amber" />
        <Stat icon="alert" label="High-risk shipments" value={k.high_risk_shipments} sub={`${b.AT_RISK} at risk · ${b.LATE} late now`} tone="red" />
        <Stat icon="activity" label="Avg predicted delay" value={k.avg_predicted_delay_hours == null ? 'n/a' : `${k.avg_predicted_delay_hours} h`} sub="after the promise, active shipments" />
      </div>

      <GateCard />

      <div className="grid xl:grid-cols-12 gap-4">
        <Card title="Live shipment map" className="xl:col-span-8">
          <State loading={map.loading && !map.data} error={map.error} onRetry={map.reload} />
          {map.data && <MapView routes={mapRoutes} vehicles={mapVehicles} disruptions={map.data.disruptions} caption={map.data.caption} height={560} onSelect={(id) => setSelected(id)} />}
        </Card>
        <Card title="Live operational activity" className="xl:col-span-4" right={<span className="text-[11px] text-slate-500">from stored records</span>}>
          <ActivityFeed limit={50} height={600} onSelect={(id) => setSelected(id)} />
        </Card>
      </div>

      <div className="grid xl:grid-cols-2 gap-4">
        <Card title="Alerts needing attention"><OpenAlerts /></Card>
        <Card title="Disruptions"><div className="grid md:grid-cols-2 gap-5">{ref.data && <Injector refData={ref.data} shipments={ct.data.shipments} />}<Disruptions /></div></Card>
      </div>

      <Card title={`Active orders and shipments (${rows.length})`} className="">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
            {sel('bucket', 'Status', [['LATE', 'Late'], ['AT_RISK', 'At risk'], ['ON_TRACK', 'On track'], ['ARRIVED_PENDING_POD', 'Arrived, POD pending'], ['DELIVERED', 'Delivered'], ['SPLIT_PARENT', 'Split parent']].map(([id, name]) => ({ id, name })))}
            {sel('route', 'Route', (ref.data?.routes ?? []).filter((r) => !r.id.endsWith('A')))}
            {sel('transporter', 'Transporter', ref.data?.transporters ?? [])}
            {sel('customer', 'Customer', ref.data?.customers ?? [])}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead><tr className="border-b border-slate-200"><th>Order / shipment</th><th>Transporter · vehicle</th><th>Status</th><th>Milestone</th><th>Promised</th><th>ETA (P50)</th><th>P(late)</th><th>Risk</th><th></th></tr></thead>
              <tbody>
                {rows.map((s) => (
                  <tr key={s.id} className={`border-b border-slate-100 hover:bg-navy-50 cursor-pointer ${s.disposition !== 'ACTIVE' ? 'opacity-60' : ''} ${selected === s.id ? 'bg-navy-50' : ''}`} onClick={() => setSelected(s.id)}>
                    <td>
                      <button className="font-semibold text-navy-700 underline" onClick={(e) => { e.stopPropagation(); nav(`/shipments/${s.id}`) }}>{s.id}</button>
                      {s.priority === 'HIGH' && <span className="ml-1 text-[10px] font-bold text-red-800 border border-red-300 rounded px-1">PRIORITY</span>}
                      <div className="text-xs text-slate-500">{s.order_id} · {s.customer_name.replace(' (fictional)', '')}</div>
                      <div className="text-xs text-slate-500">{s.route_name}{s.alternative_route_name ? ` → ${s.alternative_route_name}` : ''}</div>
                    </td>
                    <td className="text-xs">{s.transporter_name.replace(' (fictional)', '')}<div className="text-slate-500">{s.vehicle_label.replace(' (fictional)', '')} · {s.driver_name?.replace(' (fictional)', '') ?? 'no driver'}</div></td>
                    <td><BucketBadge bucket={s.bucket} /></td>
                    <td className="text-xs">{s.state_label}</td>
                    <td className="text-xs whitespace-nowrap">{fmtTime(s.promised_at)}</td>
                    <td className="text-xs whitespace-nowrap">{s.prediction ? fmtEta(s.prediction.p50_at) : s.arrived_at ? `arrived ${fmtTime(s.arrived_at)}` : '-'}</td>
                    <td>{s.prediction ? pct(s.prediction.p_late) : '-'}</td>
                    <td>{s.prediction ? <div className="flex flex-col gap-1 items-start"><RiskBadge level={s.prediction.risk_category} prefix="" />{s.prediction.data_confidence !== 'FRESH' && <ConfidenceBadge value={s.prediction.data_confidence} />}</div> : '-'}</td>
                    <td>{s.prediction && s.disposition === 'ACTIVE' && <button className="btn-secondary whitespace-nowrap !py-1" onClick={(e) => { e.stopPropagation(); nav(`/shipments/${s.id}/war-room`) }}>War Room</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 && <State empty emptyText="No shipments match these filters." />}
          </div>
          <p className="text-xs text-slate-500 mt-2">Click a row for details. {k.definition}</p>
        </Card>

      <Interventions />

      {selected && <ShipmentPanel id={selected} onClose={() => setSelected(null)} />}
      {newOrder && ref.data && <NewOrderDialog refData={ref.data} onClose={() => setNewOrder(false)} onOpenShipment={(id) => { setNewOrder(false); setSelected(id) }} />}
    </div>
  )
}
