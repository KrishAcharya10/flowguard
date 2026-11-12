// Coordinator control tower. The map is the work surface: a compact simulation toolbar and one KPI strip sit above it,
// and a sidebar (high-risk shipments, alerts, gate summary, live activity) sits beside it. Below: the shipment table,
// disruption management and pending interventions. Every number comes from the backend.
import { useMemo, useState, type ReactNode } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, refreshAll, useApi, type Alert, type CaseOut, type ControlTower as CT, type Disruption, type GateSummary, type MapData, type ReferenceData } from '../api/client'
import ActivityFeed from '../components/ActivityFeed'
import FleetMap from '../components/FleetMap'
import Icon from '../components/Icons'
import NewOrderDialog from '../components/NewOrderDialog'
import ShipmentPanel from '../components/ShipmentPanel'
import SimControl from '../components/SimControl'
import { BucketBadge, Card, ConfidenceBadge, Notice, RiskBadge, State } from '../components/ui'
import { fmtEta, fmtTime, pct } from '../lib/format'

function Kpi({ label, value, sub, tone = 'navy', icon }: { label: string; value: ReactNode; sub?: ReactNode; tone?: 'navy' | 'green' | 'amber' | 'red' | 'blue'; icon: string }) {
  const c = { navy: 'text-navy-900', green: 'text-emerald-700', amber: 'text-amber-700', red: 'text-red-700', blue: 'text-blue-700' }[tone]
  return (
    <div className="px-4 py-2.5 min-w-0">
      <div className="flex items-center gap-1.5 label !text-[10.5px]"><Icon name={icon} size={13} className={c} /><span className="truncate">{label}</span></div>
      <div className={`text-[26px] font-bold leading-tight tabular-nums ${c}`}>{value}</div>
      {sub && <div className="text-[11px] text-slate-500 leading-snug truncate" title={typeof sub === 'string' ? sub : undefined}>{sub}</div>}
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
      <div className="label mb-1.5">Disruption injector (simulated event)</div>
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
      <div className="text-xs text-slate-500 mt-1.5">Duration (min / most likely / max): {p?.duration.join(' / ')} h{p?.multiplier ? ` · factor x${p.multiplier}` : ''}</div>
      <label className="text-xs flex items-center gap-1.5 mt-1"><input type="checkbox" checked={custom} onChange={(e) => { setCustom(e.target.checked); if (p) setDur([String(p.duration[0]), String(p.duration[1]), String(p.duration[2])]) }} /> Custom duration</label>
      {custom && (
        <div className="grid grid-cols-3 gap-1.5 mt-1.5">
          {(['Min h', 'Most likely h', 'Max h'] as const).map((lbl, i) => (
            <label key={lbl} className="text-[11px] text-slate-600">{lbl}
              <input className="input" inputMode="decimal" value={dur[i]} onChange={(e) => { const d = [...dur] as [string, string, string]; d[i] = e.target.value; setDur(d) }} />
            </label>
          ))}
        </div>
      )}
      <button className="btn-danger mt-3" onClick={inject} disabled={busy || (p?.needs_shipment && !shipment)}>Inject disruption</button>
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
      <div className="label mb-1.5">Active disruptions ({active.length})</div>
      <State loading={dis.loading && !dis.data} error={dis.error} empty={!!dis.data && active.length === 0} emptyText="None right now." onRetry={dis.reload} />
      {err && <Notice kind="error">{err}</Notice>}
      <ul className="space-y-1.5">
        {active.map((d) => (
          <li key={d.id} className="text-xs flex items-center justify-between gap-2 rounded-md border-l-4 border-red-500 bg-red-50/60 px-2.5 py-1.5">
            <span><strong>{d.label}</strong> · {d.id}{d.shipment_id ? ` · ${d.shipment_id}` : ''} · since {fmtTime(d.start_at)}</span>
            <button className="btn-secondary btn-sm" onClick={() => end(d.id)}>End</button>
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
  const rows = (al.data ?? []).slice(0, 3)
  return (
    <div>
      <State loading={al.loading && !al.data} error={al.error} empty={!!al.data && al.data.length === 0} emptyText="No open alerts. Everything is on plan." onRetry={al.reload} />
      <ul className="space-y-2">
        {rows.map((a) => (
          <li key={a.id} className={`rounded-md border-l-4 bg-slate-50 px-2.5 py-2 ${a.severity === 'CRITICAL' ? 'border-red-700' : a.severity === 'HIGH' ? 'border-red-500' : 'border-amber-500'}`}>
            <div className="flex items-center justify-between gap-2"><RiskBadge level={a.severity} prefix="" /><span className="text-[11px] text-slate-500">{fmtTime(a.created_sim_at)}</span></div>
            <div className="text-[12.5px] font-semibold mt-1 leading-snug">{a.title}</div>
            {a.suggested_action && <div className="text-xs text-slate-700 mt-0.5 line-clamp-2">{a.suggested_action.replace(/^Suggested action: /, 'Suggested: ')}</div>}
            <div className="flex gap-1.5 mt-1.5">
              {a.shipment_id && <button className="btn-primary btn-sm" onClick={() => nav(`/shipments/${a.shipment_id}/war-room`)}>War Room</button>}
              <button className="btn-secondary btn-sm" onClick={() => ack(a.id)}>Acknowledge</button>
            </div>
          </li>
        ))}
      </ul>
      {(al.data?.length ?? 0) > 3 && <p className="text-xs text-slate-500 mt-1.5">+{(al.data?.length ?? 0) - 3} more in the Alerts drawer (top bar).</p>}
    </div>
  )
}

function GateCard() {
  const nav = useNavigate()
  const g = useApi<GateSummary>('/api/gate/summary')
  const d = g.data
  const usedPct = d && d.capacity ? Math.min(100, Math.round((100 * d.booked) / d.capacity)) : 0
  const t = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false })
  return (
    <Card title={`Gate slots today${d ? ` · ${d.day_label}` : ''}`} right={<button className="btn-ghost btn-sm" onClick={() => nav('/gate')}>Schedule<Icon name="arrow" size={12} /></button>}>
      <State loading={g.loading && !d} error={g.error} onRetry={g.reload} />
      {d && (
        <div>
          <div className="flex items-baseline justify-between"><span className="text-2xl font-bold text-navy-900 tabular-nums">{d.booked}<span className="text-sm font-semibold text-slate-500"> / {d.capacity}</span></span><span className="text-[11px] text-slate-500">places booked</span></div>
          <div className="h-2 rounded-full bg-slate-200 mt-1.5 overflow-hidden"><div className={`h-2 rounded-full ${usedPct >= 90 ? 'bg-amber-500' : 'bg-brand-600'}`} style={{ width: `${usedPct}%` }} /></div>
          <div className="text-[11px] text-slate-500 mt-1">{d.full_slots} full slot(s) · {d.unavailable_slots} unavailable</div>
          <ul className="mt-2 space-y-1">
            {d.upcoming.length === 0 && <li className="text-xs text-slate-500">No upcoming bookings.</li>}
            {d.upcoming.slice(0, 3).map((b) => (
              <li key={b.id} className="text-[11.5px] flex items-center gap-2"><span className="font-bold tabular-nums">{t(b.slot_start)}</span><span className="font-semibold truncate">{b.shipment_id.replace('SHP-', '')}</span><span className={`ml-auto font-bold shrink-0 ${b.status === 'CHECKED_IN' ? 'text-amber-700' : 'text-sky-700'}`}>{b.status.replace('_', ' ')}</span></li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  )
}

function Priority({ rows, selected, onPick }: { rows: CT['shipments']; selected: string | null; onPick: (id: string) => void }) {
  const hot = rows.filter((s) => s.disposition === 'ACTIVE' && s.prediction && (s.bucket === 'LATE' || s.prediction.risk_category === 'HIGH'))
    .sort((a, b) => (b.prediction?.risk_index ?? 0) - (a.prediction?.risk_index ?? 0)).slice(0, 5)
  return (
    <Card title="High-risk shipments" right={<span className={`chip ${hot.length ? 'bg-red-50 text-red-800 border-red-200' : 'bg-slate-50 text-slate-600 border-slate-200'}`}>{hot.length}</span>}>
      {hot.length === 0 && <p className="text-xs text-slate-500">No shipment is at high risk right now.</p>}
      <ul className="space-y-1" data-testid="priority-list">
        {hot.map((s) => (
          <li key={s.id}>
            <button onClick={() => onPick(s.id)} aria-pressed={selected === s.id}
              className={`w-full text-left rounded-md border px-2.5 py-1.5 flex items-center gap-2 transition-colors ${selected === s.id ? 'border-navy-700 bg-navy-50' : 'border-slate-200 hover:bg-slate-50'}`}>
              <span className={`h-8 w-1 rounded-full shrink-0 ${s.prediction!.risk_category === 'HIGH' ? 'bg-red-600' : 'bg-amber-500'}`} />
              <span className="min-w-0 flex-1">
                <span className="block text-[12.5px] font-bold text-navy-900 truncate">{s.id.replace('SHP-', '')}{s.priority === 'HIGH' && <span className="ml-1 text-[9px] font-bold text-red-800 border border-red-300 rounded px-1 align-middle">PRIORITY</span>}</span>
                <span className="block text-[11px] text-slate-500 truncate">{s.customer_name.replace(' (fictional)', '')}</span>
              </span>
              <span className="text-right shrink-0"><span className="block text-[13px] font-bold tabular-nums text-red-700">{pct(s.prediction!.p_late)}</span><span className="block text-[10px] text-slate-500">P(late)</span></span>
            </button>
          </li>
        ))}
      </ul>
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
    <Card title="Interventions and approvals" right={<span className={`chip ${pending ? 'bg-amber-50 text-amber-900 border-amber-300' : 'bg-slate-50 text-slate-700 border-slate-200'}`}>{pending} awaiting approval</span>}>
      <State loading={iv.loading && !iv.data} error={iv.error} empty={!!iv.data && iv.data.length === 0} emptyText="No decision cases yet. Open a shipment's War Room to compare options." onRetry={iv.reload} />
      <ul className="divide-y divide-slate-100">
        {rows.map((c) => (
          <li key={c.id} className="py-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="font-semibold">#{c.id}</span>
            <Link className="text-navy-700 hover:underline" to={`/shipments/${c.shipment_id}/war-room`}>{c.shipment_id}</Link>
            <span className="text-xs text-slate-600">recommended: {c.recommendation.code.replace(/_/g, ' ').toLowerCase()}</span>
            {chosen(c) && <span className="text-xs">chosen: <strong>{chosen(c)}</strong>{c.is_override ? ' (override)' : ''}</span>}
            <span className={`ml-auto chip ${c.status === 'APPLIED' || c.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-900 border-emerald-200' : c.status === 'AWAITING_APPROVAL' ? 'bg-amber-50 text-amber-900 border-amber-300' : 'bg-slate-50 text-slate-700 border-slate-200'}`}>{c.status.replace('_', ' ')}</span>
            {c.status === 'AWAITING_APPROVAL' && !c.is_stale && <button className="btn-primary btn-sm" onClick={() => nav(`/shipments/${c.shipment_id}/war-room`)}>Review</button>}
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
  const [selected, setSelected] = useState<string | null>(null)       // shipment drawer (table, activity feed)
  const [mapSel, setMapSel] = useState<string | null>(null)           // vehicle selected on the map
  const [newOrder, setNewOrder] = useState(false)

  const rows = useMemo(() => (ct.data?.shipments ?? []).filter((s) =>
    (!f.bucket || s.bucket === f.bucket) && (!f.route || s.route_id === f.route) &&
    (!f.transporter || s.transporter_id === f.transporter) && (!f.customer || s.customer_id === f.customer))
    .sort((a, b) => (b.prediction?.risk_index ?? -1) - (a.prediction?.risk_index ?? -1) || (a.priority === 'HIGH' ? -1 : 1)), [ct.data, f])

  if (!ct.data) return <State loading={ct.loading} error={ct.error} onRetry={ct.reload} />
  const k = ct.data.kpis
  const b = k.buckets
  const sel = (key: keyof typeof f, label: string, opts: { id: string; name: string }[]) => (
    <label className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">{label}
      <select className="input mt-1 normal-case tracking-normal font-normal" value={f[key]} onChange={(e) => setF({ ...f, [key]: e.target.value })}>
        <option value="">All</option>
        {opts.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
      </select>
    </label>
  )
  const latePct = (p: number) => (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-14 rounded-full bg-slate-200 overflow-hidden"><div className={`h-1.5 rounded-full ${p >= 0.5 ? 'bg-red-600' : p >= 0.2 ? 'bg-amber-500' : 'bg-emerald-500'}`} style={{ width: `${Math.round(p * 100)}%` }} /></div>
      <span className="tabular-nums text-xs font-semibold">{pct(p)}</span>
    </div>
  )

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
        <h1 className="text-[22px] font-bold leading-tight">Control Tower</h1>
        <p className="hidden md:block text-[13px] text-slate-600">Plant X to the customer's gate: where every shipment is, which will be late, and what to do about it.</p>
        <button className="btn-primary ml-auto self-center" onClick={() => setNewOrder(true)} disabled={!ref.data}><Icon name="plus" size={15} />New order</button>
      </div>

      <SimControl demoMode={ref.data?.demo_mode ?? true} />

      <section className="card grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 divide-x divide-y xl:divide-y-0 divide-slate-200 overflow-hidden" aria-label="Key figures">
        <Kpi icon="box" label="Active orders" value={k.active_orders} sub={`${k.active_shipments} shipments in progress`} />
        <Kpi icon="truck" label="Active shipments" value={k.active_shipments} sub={`${b.ARRIVED_PENDING_POD} arrived, POD pending`} tone="blue" />
        <Kpi icon="check" label="On-time deliveries" value={k.on_time_pct == null ? 'n/a' : `${k.on_time_pct}%`} sub={`${k.orders_on_time} of ${k.orders_completed} orders, last ${k.window_days} days`} tone="green" />
        <Kpi icon="clock" label="Delayed shipments" value={k.delayed_shipments} sub="late now or predicted late" tone={k.delayed_shipments ? 'amber' : 'navy'} />
        <Kpi icon="alert" label="High-risk shipments" value={k.high_risk_shipments} sub={`${b.AT_RISK} at risk · ${b.LATE} late now`} tone={k.high_risk_shipments ? 'red' : 'navy'} />
        <Kpi icon="activity" label="Avg predicted delay" value={k.avg_predicted_delay_hours == null ? 'n/a' : `${k.avg_predicted_delay_hours} h`} sub="after the promise, active shipments" />
      </section>

      <div className="grid gap-4 min-[1400px]:grid-cols-[minmax(0,1fr)_20.5rem]">
        <section className="card p-3" aria-label="Live shipment map">
          <State loading={map.loading && !map.data} error={map.error} onRetry={map.reload} />
          {map.data && <FleetMap data={map.data} shipments={ct.data.shipments} selected={mapSel} onSelect={setMapSel} height="clamp(560px, calc(100vh - 300px), 800px)" />}
        </section>
        <aside className="relative min-[1400px]:min-h-[420px]" aria-label="Operational sidebar">
          <div className="grid md:grid-cols-2 gap-3 items-start min-[1400px]:absolute min-[1400px]:inset-0 min-[1400px]:overflow-y-auto min-[1400px]:flex min-[1400px]:flex-col min-[1400px]:pr-1">
            <Priority rows={ct.data.shipments} selected={mapSel} onPick={setMapSel} />
            <Card title="Alerts needing attention"><OpenAlerts /></Card>
            <GateCard />
            <Card title="Live operational activity" right={<span className="text-[11px] text-slate-500">stored records</span>}>
              <ActivityFeed limit={50} height={340} onSelect={(id) => setSelected(id)} />
            </Card>
          </div>
        </aside>
      </div>

      <Card title={`Active orders and shipments (${rows.length})`}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
          {sel('bucket', 'Status', [['LATE', 'Late'], ['AT_RISK', 'At risk'], ['ON_TRACK', 'On track'], ['ARRIVED_PENDING_POD', 'Arrived, POD pending'], ['DELIVERED', 'Delivered'], ['SPLIT_PARENT', 'Split parent']].map(([id, name]) => ({ id, name })))}
          {sel('route', 'Route', (ref.data?.routes ?? []).filter((r) => !r.id.endsWith('A')))}
          {sel('transporter', 'Transporter', ref.data?.transporters ?? [])}
          {sel('customer', 'Customer', ref.data?.customers ?? [])}
        </div>
        <div className="overflow-x-auto -mx-4 border-t border-slate-200">
          <table className="w-full">
            <thead><tr className="border-b border-slate-200"><th className="min-w-[230px]">Order / shipment</th><th className="min-w-[170px]">Transporter · vehicle</th><th>Status</th><th>Milestone</th><th>Promised</th><th>ETA (P50)</th><th>P(late)</th><th>Risk</th><th></th></tr></thead>
            <tbody>
              {rows.map((s) => (
                <tr key={s.id} className={`border-b border-slate-100 hover:bg-navy-50/70 cursor-pointer ${s.disposition !== 'ACTIVE' ? 'opacity-60' : ''} ${selected === s.id || mapSel === s.id ? 'bg-navy-50' : ''}`} onClick={() => setSelected(s.id)}>
                  <td className="min-w-[230px]">
                    <button className="font-semibold text-navy-700 hover:underline whitespace-nowrap" onClick={(e) => { e.stopPropagation(); nav(`/shipments/${s.id}`) }}>{s.id}</button>
                    {s.priority === 'HIGH' && <span className="ml-1 text-[10px] font-bold text-red-800 border border-red-300 rounded px-1">PRIORITY</span>}
                    <div className="text-xs text-slate-500">{s.order_id} · {s.customer_name.replace(' (fictional)', '')}</div>
                    <div className="text-xs text-slate-500">{s.route_name}{s.alternative_route_name ? ` → ${s.alternative_route_name}` : ''}</div>
                  </td>
                  <td className="text-xs min-w-[170px]">{s.transporter_name.replace(' (fictional)', '')}<div className="text-slate-500">{s.vehicle_label.replace(' (fictional)', '')} · {s.driver_name?.replace(' (fictional)', '') ?? 'no driver'}</div></td>
                  <td><BucketBadge bucket={s.bucket} /></td>
                  <td className="text-xs">{s.state_label}</td>
                  <td className="text-xs whitespace-nowrap">{fmtTime(s.promised_at)}</td>
                  <td className="text-xs whitespace-nowrap">{s.prediction ? fmtEta(s.prediction.p50_at) : s.arrived_at ? `arrived ${fmtTime(s.arrived_at)}` : '-'}</td>
                  <td>{s.prediction ? latePct(s.prediction.p_late) : '-'}</td>
                  <td>{s.prediction ? <div className="flex flex-col gap-1 items-start"><RiskBadge level={s.prediction.risk_category} prefix="" />{s.prediction.data_confidence !== 'FRESH' && <ConfidenceBadge value={s.prediction.data_confidence} />}</div> : '-'}</td>
                  <td className="whitespace-nowrap">{s.prediction && s.disposition === 'ACTIVE' && <button className="btn-secondary btn-sm" onClick={(e) => { e.stopPropagation(); nav(`/shipments/${s.id}/war-room`) }}>War Room</button>}
                    {s.bucket === 'ARRIVED_PENDING_POD' && <button className="btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); nav(`/documents?order=${s.order_id}`) }}>Add proof of delivery</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <State empty emptyText="No shipments match these filters." />}
        </div>
        <p className="text-xs text-slate-500 mt-2">Click a row for details. {k.definition}</p>
      </Card>

      <div className="grid xl:grid-cols-2 gap-4">
        <Card title="Disruption management"><div className="grid md:grid-cols-2 gap-5">{ref.data && <Injector refData={ref.data} shipments={ct.data.shipments} />}<Disruptions /></div></Card>
        <Interventions />
      </div>

      {selected && <ShipmentPanel id={selected} onClose={() => setSelected(null)} />}
      {newOrder && ref.data && <NewOrderDialog refData={ref.data} onClose={() => setNewOrder(false)} onOpenShipment={(id) => { setNewOrder(false); setSelected(id) }} />}
    </div>
  )
}
