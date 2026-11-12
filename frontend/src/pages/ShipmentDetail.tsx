import { Link, useParams } from 'react-router-dom'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, refreshAll, useApi, type Booking, type EventRow, type Prediction, type ShipmentDetail as SD } from '../api/client'
import DocumentsPanel from '../components/Documents'
import { BucketBadge, Card, ConfidenceBadge, MilestoneBar, Notice, RiskBadge, State } from '../components/ui'
import { fmtEta, fmtTime, hoursBetween, hrs, pct, signed } from '../lib/format'

function EtaIntelligence({ s, p }: { s: SD; p: Prediction }) {
  const r = p.reasons
  const max = Math.max(0.5, ...r.chips.map((c) => Math.abs(c.hours)))
  const lateBy = hoursBetween(p.p50_at, s.promised_at)
  return (
    <Card title="ETA intelligence" right={<div className="flex gap-2"><RiskBadge level={p.risk_category} /><ConfidenceBadge value={p.data_confidence} /></div>}>
      <div className="grid sm:grid-cols-4 gap-3 text-sm">
        <div><div className="label">Original promise</div><div className="font-bold">{fmtTime(s.promised_at)}</div></div>
        <div><div className="label">ETA (P50)</div><div className="font-bold">{fmtEta(p.p50_at)}</div><div className={`text-xs ${lateBy > 0 ? 'text-red-700' : 'text-green-700'}`}>{lateBy > 0 ? `${lateBy.toFixed(1)} h after the promise` : `${(-lateBy).toFixed(1)} h before the promise`}</div></div>
        <div><div className="label">Range (P10 – P90)</div><div className="font-semibold">{fmtEta(p.p10_at)} – {fmtEta(p.p90_at)}</div></div>
        <div><div className="label">Risk index</div><div className="font-bold">{p.risk_index} / 100</div><div className="text-xs text-slate-500">a ranking score, not a probability</div></div>
      </div>
      <div className="grid sm:grid-cols-2 gap-3 mt-3">
        <div className="rounded-md bg-slate-50 border border-slate-200 p-3"><div className="label">P(late)</div><div className="text-2xl font-bold">{pct(p.p_late)}</div><div className="text-xs text-slate-500">expected late hours {hrs(r.expected_late_hours)}</div></div>
        <div className="rounded-md bg-slate-50 border border-slate-200 p-3"><div className="label">P(customer stock-out)</div><div className="text-2xl font-bold">{r.stock_available ? pct(p.p_stockout) : 'n/a'}</div><div className="text-xs text-slate-500">{r.stock_available ? `stock runs out ${fmtTime(r.stock_depletion_at)} · expected stock-out ${hrs(r.expected_stockout_hours)}` : 'Stock data unavailable'}</div></div>
      </div>

      <h3 className="label mt-4 mb-1">Why: mean contribution of each cause (hours vs the undisturbed baseline)</h3>
      <ul className="space-y-1">
        {r.chips.filter((c) => Math.abs(c.hours) >= 0.005 || c.key === 'variability').map((c) => (
          <li key={c.key} className="flex items-center gap-2 text-sm">
            <span className="w-64 shrink-0">{c.label}</span>
            <span className="flex-1 h-3 bg-slate-100 rounded overflow-hidden"><span className={`block h-3 ${c.hours >= 0 ? 'bg-navy-700' : 'bg-green-600'}`} style={{ width: `${Math.min(100, (Math.abs(c.hours) / max) * 100)}%` }} /></span>
            <span className="w-16 text-right font-semibold tabular-nums">{signed(c.hours, 2)} h</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-slate-500 mt-1">These explain the MEAN arrival ({fmtEta(r.mean_at)}) versus the baseline ({fmtEta(r.baseline_at)}). P50 and P90 are shown separately above.</p>
      <ul className="flex flex-wrap gap-2 mt-2">{r.notes.map((n) => <li key={n} className="text-xs rounded-full border border-slate-300 bg-white px-2 py-0.5">{n}</li>)}</ul>
      {r.p50_change && Math.abs(r.p50_change.hours) >= 0.05 && (
        <div className="mt-3"><Notice kind={r.p50_change.hours > 0 ? 'warn' : 'ok'}>P50 moved <strong>{signed(r.p50_change.hours)} h</strong> since {fmtTime(r.p50_change.since)}: {r.p50_change.trigger}.</Notice></div>
      )}
      <p className="text-xs text-slate-500 mt-3">{r.method}</p>
    </Card>
  )
}

export default function ShipmentDetail() {
  const { id } = useParams()
  const s = useApi<SD>(`/api/shipments/${id}`)
  const hist = useApi<Prediction[]>(`/api/shipments/${id}/prediction?history=true`)
  const events = useApi<EventRow[]>(`/api/shipments/${id}/events`)
  const gate = useApi<Booking[]>(`/api/gate/bookings?shipment_id=${id}`)
  if (!s.data) return <State loading={s.loading} error={s.error} onRetry={s.reload} />
  const d = s.data
  const p = d.prediction
  const recalc = async () => { await api(`/api/shipments/${d.id}/recalculate`, { method: 'POST' }); refreshAll() }
  const series = [...(hist.data ?? [])].reverse().map((x, i) => ({ i: i + 1, p50: +hoursBetween(x.p50_at, d.promised_at).toFixed(2), p90: +hoursBetween(x.p90_at, d.promised_at).toFixed(2), p10: +hoursBetween(x.p10_at, d.promised_at).toFixed(2), trigger: x.trigger }))

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to="/tower" className="text-sm underline text-navy-700">← Control Tower</Link>
        <h1 className="text-xl font-bold text-navy-900">{d.id}</h1>
        <BucketBadge bucket={d.bucket} />
        {d.priority === 'HIGH' && <span className="text-xs font-bold text-red-800 border border-red-300 rounded px-1">PRIORITY ORDER</span>}
        <div className="ml-auto flex gap-2">
          {p && <button className="btn-secondary" onClick={recalc}>Recalculate</button>}
          {p && d.disposition === 'ACTIVE' && <Link className="btn-primary" to={`/shipments/${d.id}/war-room`}>Open War Room</Link>}
        </div>
      </div>
      {d.disposition === 'SPLIT_PARENT' && <Notice kind="info">This shipment was split. It is not a delivery lot and is excluded from delivery KPIs. Child lots: {d.child_shipment_ids.map((c) => <Link key={c} className="underline font-semibold mx-1" to={`/shipments/${c}`}>{c}</Link>)}</Notice>}

      <Card>
        <div className="grid md:grid-cols-4 gap-3 text-sm mb-4">
          <div><div className="label">Order / customer</div>{d.order_id} · {d.customer_name}</div>
          <div><div className="label">Product / quantity</div>{d.product_code} · {d.quantity_tonnes} t{d.lot_type !== 'SINGLE' ? ` (${d.lot_type.toLowerCase()} lot)` : ''}</div>
          <div><div className="label">Route</div>{d.route_name}{d.alternative_route_name ? <span className="text-violet-800 font-semibold"> → via {d.alternative_route_name}</span> : ''} · {Math.round(d.last_progress_km)} / {Math.round(d.total_km)} km</div>
          <div><div className="label">Transporter / vehicle</div>{d.transporter_name} · {d.vehicle_label}</div>
        </div>
        <MilestoneBar items={d.milestones} />
        {d.last_telemetry_at && d.state === 'IN_TRANSIT' && <p className="text-xs text-slate-500 mt-2">Last reported position: {fmtTime(d.last_telemetry_at)}. The map always shows the last REPORTED position, never an assumed one.</p>}
      </Card>

      {d.disruptions.length > 0 && <Notice kind="warn"><strong>Active disruptions affecting this shipment:</strong> {d.disruptions.map((x) => `${x.label} (${x.id}, since ${fmtTime(x.start_at)}, expected ${x.dur_min_h}–${x.dur_max_h} h)`).join('; ')}</Notice>}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          {p ? <EtaIntelligence s={d} p={p} /> : <Card title="ETA intelligence"><p className="text-sm">{d.arrived_at ? `Arrived at the customer gate ${fmtTime(d.arrived_at)} (${hoursBetween(d.arrived_at, d.promised_at) <= 0 ? 'on time' : `${hoursBetween(d.arrived_at, d.promised_at).toFixed(1)} h late`}). Actuals are shown instead of a prediction.` : 'No prediction for this shipment.'}</p></Card>}
          <Card title="How the prediction changed (hours relative to the promise; above 0 = late)">
            <State loading={hist.loading && !hist.data} error={hist.error} empty={series.length === 0} emptyText="No prediction history." onRetry={hist.reload} />
            {series.length > 0 && (
              <div style={{ height: 200 }}>
                <ResponsiveContainer>
                  <LineChart data={series} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
                    <CartesianGrid stroke="#e2e8f0" />
                    <XAxis dataKey="i" tick={{ fontSize: 11 }} label={{ value: 'prediction #', position: 'insideBottomRight', offset: 0, fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 11 }} unit=" h" />
                    <Tooltip formatter={(v: number, n: string) => [`${v} h`, n]} labelFormatter={(l) => `#${l}: ${series[Number(l) - 1]?.trigger ?? ''}`} />
                    <ReferenceLine y={0} stroke="#b91c1c" strokeDasharray="4 4" label={{ value: 'promise', fontSize: 10, fill: '#b91c1c' }} />
                    <Line dataKey="p90" name="P90" stroke="#94a3b8" dot={false} isAnimationActive={false} />
                    <Line dataKey="p50" name="P50" stroke="#12305a" strokeWidth={2} isAnimationActive={false} />
                    <Line dataKey="p10" name="P10" stroke="#94a3b8" dot={false} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </Card>
        </div>
        <div className="space-y-4">
          <Card title="Customer stock cover">
            {d.stock.available ? (
              <dl className="text-sm grid grid-cols-2 gap-y-1">
                <dt className="text-slate-500">Inventory</dt><dd>{d.stock.inventory_tonnes} t at {fmtTime(d.stock.measured_at)}</dd>
                <dt className="text-slate-500">Consumption</dt><dd>{d.stock.consumption_tph} t/h</dd>
                <dt className="text-slate-500">Unloading</dt><dd>{d.stock.unloading_hours} h</dd>
                <dt className="text-slate-500">Stock runs out</dt><dd className="font-semibold">{fmtTime(d.stock.depletion_at)}</dd>
              </dl>
            ) : <p className="text-sm font-semibold">Stock data unavailable</p>}
            <p className="text-xs text-slate-500 mt-2">{d.stock.note}</p>
          </Card>
          <Card title="Event log">
            <State loading={events.loading && !events.data} error={events.error} empty={!!events.data && events.data.length === 0} onRetry={events.reload} />
            <ul className="space-y-2 max-h-80 overflow-y-auto">
              {[...(events.data ?? [])].reverse().map((e) => (
                <li key={e.id} className="text-sm border-l-2 border-navy-700 pl-2">
                  <div className="text-xs text-slate-500">{fmtTime(e.occurred_at)} · {e.type.replace(/_/g, ' ').toLowerCase()} · {e.source.toLowerCase()}</div>
                  {e.note}
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
      <Card title="Gate appointment">
        {gate.data && gate.data.length > 0 ? (
          <ul className="space-y-1.5">{gate.data.map((b) => (
            <li key={b.id} className="flex flex-wrap items-center gap-3 text-sm"><strong className="tabular-nums">{new Date(b.slot_start).toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })} IST</strong><span className="text-slate-600">{b.vehicle_label.replace(' (fictional)', '')} · {b.driver_name?.replace(' (fictional)', '')}</span><span className="font-bold text-navy-800">{b.status.replace('_', ' ')}</span></li>
          ))}</ul>
        ) : <p className="text-sm text-slate-600">No gate slot booked. Book one in <a className="underline text-navy-700" href="/gate">Gate slots</a>.</p>}
      </Card>
      <Card title={`Documents · order ${d.order_id}`}><DocumentsPanel orderId={d.order_id} /></Card>
    </div>
  )
}
