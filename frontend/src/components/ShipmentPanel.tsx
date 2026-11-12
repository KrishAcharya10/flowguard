// Shipment detail panel: opens beside the Control Tower so the coordinator never loses the overview.
import { useNavigate } from 'react-router-dom'
import { useApi, type EventRow, type ShipmentDetail } from '../api/client'
import { fmtEta, fmtTime, hoursBetween, pct, signed } from '../lib/format'
import { BucketBadge, ConfidenceBadge, MilestoneBar, RiskBadge, State } from './ui'

export default function ShipmentPanel({ id, onClose }: { id: string; onClose: () => void }) {
  const nav = useNavigate()
  const s = useApi<ShipmentDetail>(`/api/shipments/${id}`)
  const ev = useApi<EventRow[]>(`/api/shipments/${id}/events`)
  const d = s.data
  const p = d?.prediction
  return (
    <div className="fixed inset-0 z-[950] flex justify-end" role="dialog" aria-modal="true" aria-label={`Shipment ${id}`}>
      <button className="flex-1 bg-black/20" aria-label="Close shipment panel" onClick={onClose} />
      <aside className="w-full max-w-lg bg-white h-full overflow-y-auto shadow-2xl">
        <div className="sticky top-0 bg-white border-b border-slate-200 px-4 py-3 flex items-center gap-2 z-10">
          <h2 className="text-lg font-bold text-navy-900">{id}</h2>
          {d && <BucketBadge bucket={d.bucket} />}
          <button className="btn-secondary ml-auto" onClick={onClose}>Close</button>
        </div>
        <div className="p-4 space-y-4">
          <State loading={s.loading && !d} error={s.error} onRetry={s.reload} />
          {d && (
            <>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
                <dt className="text-slate-500">Order</dt><dd>{d.order_id}{d.priority === 'HIGH' && <span className="ml-1 text-[10px] font-bold text-red-800 border border-red-300 rounded px-1">PRIORITY</span>}</dd>
                <dt className="text-slate-500">Customer</dt><dd>{d.customer_name.replace(' (fictional)', '')}</dd>
                <dt className="text-slate-500">Load</dt><dd>{d.product_code} · {d.quantity_tonnes} t</dd>
                <dt className="text-slate-500">Route</dt><dd>{d.route_name}{d.alternative_route_name ? ` → via ${d.alternative_route_name}` : ''}</dd>
                <dt className="text-slate-500">Transporter</dt><dd>{d.transporter_name.replace(' (fictional)', '')}</dd>
                <dt className="text-slate-500">Driver / vehicle</dt><dd>{d.driver_name?.replace(' (fictional)', '') ?? '-'} · {d.vehicle_label.replace(' (fictional)', '')}</dd>
                <dt className="text-slate-500">Progress</dt><dd>{Math.round(d.last_progress_km)} of {Math.round(d.total_km)} km</dd>
              </dl>
              <MilestoneBar items={d.milestones} />
              {p ? (
                <div className="rounded-lg border border-slate-200 p-3 space-y-2">
                  <div className="flex flex-wrap items-center gap-2"><RiskBadge level={p.risk_category} /><ConfidenceBadge value={p.data_confidence} /><span className="text-xs text-slate-500">risk index {p.risk_index}/100</span></div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div><div className="label">Original promise</div><strong>{fmtTime(d.promised_at)}</strong></div>
                    <div><div className="label">ETA (P50)</div><strong>{fmtEta(p.p50_at)}</strong>
                      <div className={`text-xs ${hoursBetween(p.p50_at, d.promised_at) > 0 ? 'text-red-700' : 'text-green-700'}`}>{hoursBetween(p.p50_at, d.promised_at) > 0 ? `${hoursBetween(p.p50_at, d.promised_at).toFixed(1)} h after the promise` : `${(-hoursBetween(p.p50_at, d.promised_at)).toFixed(1)} h before the promise`}</div></div>
                    <div><div className="label">Range P10–P90</div>{fmtEta(p.p10_at)} – {fmtEta(p.p90_at)}</div>
                    <div><div className="label">P(late) / P(stock-out)</div><strong>{pct(p.p_late)}</strong> / <strong>{d.stock.available ? pct(p.p_stockout) : 'n/a'}</strong></div>
                  </div>
                  <div>
                    <div className="label mb-1">Why (mean hours vs an undisturbed trip)</div>
                    <ul className="text-sm space-y-0.5">
                      {p.reasons.chips.filter((c) => Math.abs(c.hours) >= 0.05).sort((a, b) => Math.abs(b.hours) - Math.abs(a.hours)).slice(0, 4).map((c) => (
                        <li key={c.key} className="flex justify-between"><span>{c.label}</span><span className="font-semibold tabular-nums">{signed(c.hours, 2)} h</span></li>
                      ))}
                    </ul>
                    {p.reasons.p50_change && Math.abs(p.reasons.p50_change.hours) >= 0.05 && <p className="text-xs text-amber-800 mt-1">P50 moved {signed(p.reasons.p50_change.hours)} h: {p.reasons.p50_change.trigger}.</p>}
                  </div>
                </div>
              ) : <p className="text-sm text-slate-600">{d.arrived_at ? `Arrived at the customer gate ${fmtTime(d.arrived_at)}.` : 'No prediction for this shipment.'}</p>}
              {d.disruptions.length > 0 && <div className="text-sm rounded-md bg-amber-50 border border-amber-300 text-amber-900 p-2"><strong>Active disruptions:</strong> {d.disruptions.map((x) => x.label).join('; ')}</div>}
              <div className="flex flex-wrap gap-2">
                {p && d.disposition === 'ACTIVE' && <button className="btn-primary" onClick={() => nav(`/shipments/${id}/war-room`)}>Open War Room</button>}
                <button className="btn-secondary" onClick={() => nav(`/shipments/${id}`)}>Full details</button>
              </div>
              <div>
                <div className="label mb-1">Recent events</div>
                <State loading={ev.loading && !ev.data} error={ev.error} />
                <ul className="space-y-1.5">
                  {[...(ev.data ?? [])].reverse().slice(0, 7).map((e) => (
                    <li key={e.id} className="text-sm border-l-2 border-navy-700 pl-2"><div className="text-xs text-slate-500">{fmtTime(e.occurred_at)} · {e.source.toLowerCase()}</div>{e.note}</li>
                  ))}
                </ul>
              </div>
            </>
          )}
        </div>
      </aside>
    </div>
  )
}
