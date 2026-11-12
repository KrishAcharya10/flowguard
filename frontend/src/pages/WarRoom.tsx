import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, refreshAll, useApi, type CaseOut, type Clock, type Scenario, type ShipmentDetail } from '../api/client'
import { Card, Modelled, Notice, State } from '../components/ui'
import { fmtEta, fmtTime, hrs, pct, rs } from '../lib/format'

const NAME: Record<string, string> = { CONTINUE: 'Continue', REROUTE: 'Reroute', SPLIT: 'Split shipment' }

function Row({ label, hint, cells }: { label: string; hint?: string; cells: ReactNode[] }) {
  return (
    <tr className="border-b border-slate-100">
      <th scope="row" className="!normal-case !text-sm !font-medium !text-slate-700 w-56">{label}{hint && <div className="text-[11px] font-normal text-slate-500">{hint}</div>}</th>
      {cells.map((c, i) => <td key={i} className="tabular-nums">{c}</td>)}
    </tr>
  )
}

export default function WarRoom() {
  const { id } = useParams()
  const ship = useApi<ShipmentDetail>(`/api/shipments/${id}`)
  const c = useApi<CaseOut | null>(`/api/shipments/${id}/scenarios`)
  const clock = useApi<Clock>('/api/simulation/clock')
  const running = !!clock.data && !clock.data.paused          // a decision is only valid for a frozen situation
  const pauseClock = () => act(() => api('/api/simulation/clock/control', { method: 'POST', body: { paused: true } }), 'Simulation paused. You can run the scenarios and approve now.')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error' | 'warn'; text: string } | null>(null)
  const [reason, setReason] = useState('')
  const [showCases, setShowCases] = useState(false)

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMsg(null)
    try { await fn(); setMsg({ kind: 'ok', text: ok }) } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false); refreshAll() }
  }
  const run = () => act(() => api(`/api/shipments/${id}/scenarios`, { method: 'POST' }), 'Scenarios simulated on the current state.')
  const approve = (s: Scenario) => act(() => api(`/api/interventions/${c.data!.id}/approve`, { method: 'POST', body: { selected_scenario_id: s.id, override_reason: reason || null } }), `${NAME[s.code]} approved and applied. The customer has been notified.`)
  const reject = () => act(() => api(`/api/interventions/${c.data!.id}/reject`, { method: 'POST', body: { reason: reason || null } }), 'Case rejected. Nothing was changed.')

  const kase = c.data
  const rec = kase?.recommendation
  const open = kase?.status === 'AWAITING_APPROVAL' && !kase.is_stale
  const cols = kase?.scenarios ?? []
  const cell = (fn: (s: Scenario) => ReactNode) => cols.map((s) => (s.eligible && s.metrics ? fn(s) : <span className="text-slate-400">-</span>))
  const bannerKind = rec?.code === 'NO_FEASIBLE_OPTION' ? 'bg-red-700 text-white' : rec?.code === 'NO_JUSTIFIED_INTERVENTION' ? 'bg-slate-700 text-white' : 'bg-green-700 text-white'

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link to={`/shipments/${id}`} className="text-sm underline text-navy-700">← {id}</Link>
        <h1 className="text-xl font-bold text-navy-900">War Room · {id}</h1>
        <span className="text-xs text-slate-600 border border-slate-300 rounded px-2 py-0.5">Single-shipment decision support. Not fleet optimisation.</span>
        <button className="btn-primary ml-auto" onClick={run} disabled={busy || running}>{kase ? 'Re-run scenarios' : 'Run scenarios'}</button>
      </div>
      {running && (
        <Notice kind="warn">
          <div className="flex flex-wrap items-center gap-3"><span><strong>The simulation clock is running.</strong> Scenarios go out of date every time the clock moves, so you can only run or approve them while it is paused.</span>
            <button className="btn-primary" onClick={pauseClock} disabled={busy}>Pause simulation</button></div>
        </Notice>
      )}
      {ship.data && <p className="text-sm text-slate-700">{ship.data.customer_name} · {ship.data.product_code} · {ship.data.quantity_tonnes} t · {ship.data.state_label} · original promise <strong>{fmtTime(ship.data.promised_at)}</strong></p>}
      <State loading={c.loading && !kase} error={c.error} onRetry={c.reload} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {!c.loading && !c.error && !kase && <Notice kind="info">No scenarios yet. Press <strong>Run scenarios</strong> to compare Continue, Reroute and Split on the same simulated conditions.</Notice>}

      {kase && rec && (
        <>
          {kase.is_stale && <Notice kind="warn"><strong>These scenarios are out of date</strong> because {kase.stale_reason}. Re-run them before approving.</Notice>}
          {kase.status !== 'AWAITING_APPROVAL' && <Notice kind={kase.status === 'APPLIED' || kase.status === 'COMPLETED' ? 'ok' : 'info'}>Case #{kase.id} is <strong>{kase.status}</strong>{kase.decided_by_name ? ` (by ${kase.decided_by_name} at ${fmtTime(kase.decided_sim_at)})` : ''}.{kase.is_override ? ` CONSTRAINT OVERRIDE - reason: ${kase.override_reason}` : ''}</Notice>}

          <div className={`rounded-lg p-4 ${bannerKind}`}>
            <div className="text-xs font-semibold opacity-80">RECOMMENDATION <Modelled /></div>
            <div className="text-2xl font-bold mt-1">{rec.banner}</div>
            <ul className="mt-2 text-sm space-y-0.5 list-disc pl-5">{(rec.explanation ?? []).map((l) => <li key={l}>{l}</li>)}</ul>
          </div>

          <Card title="Scenario comparison (same random conditions for every option)">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th></th>
                    {cols.map((s) => (
                      <th key={s.code} className={`!text-sm !normal-case ${!s.eligible ? 'opacity-50' : ''}`}>
                        <div className="text-navy-900 font-bold">{NAME[s.code]}</div>
                        <div className="font-normal text-xs text-slate-600 normal-case">{s.eligible ? s.summary : 'Not eligible'}</div>
                        <div className="mt-1 flex flex-wrap gap-1">
                          {rec.option_code === s.code && rec.code !== 'NO_FEASIBLE_OPTION' && <span className="rounded bg-green-700 text-white text-[10px] px-1.5 py-0.5">★ RECOMMENDED</span>}
                          {rec.least_violating_code === s.code && <span className="rounded bg-slate-200 text-slate-800 text-[10px] px-1.5 py-0.5">least-violating (info only)</span>}
                          {s.eligible && (s.feasible ? <span className="rounded bg-green-100 text-green-900 text-[10px] px-1.5 py-0.5">✓ feasible</span> : <span className="rounded bg-red-100 text-red-900 text-[10px] px-1.5 py-0.5">✕ violates a constraint</span>)}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <Row label="Median arrival (P50)" cells={cell((s) => fmtEta(s.metrics!.p50_at))} />
                  <Row label="Late-case arrival (P90)" cells={cell((s) => fmtEta(s.metrics!.p90_at))} />
                  <Row label="P(late)" hint="any lot after the promise" cells={cell((s) => pct(s.metrics!.p_late))} />
                  <Row label="P(customer stock-out)" cells={cell((s) => pct(s.metrics!.p_stockout))} />
                  <Row label="Expected late hours" cells={cell((s) => hrs(s.metrics!.exp_late_h, 2))} />
                  <Row label="Expected stock-out hours" cells={cell((s) => hrs(s.metrics!.exp_stockout_h, 2))} />
                  <Row label="Extra freight" hint="certain if chosen" cells={cell((s) => rs(s.metrics!.freight))} />
                  <Row label="SLA cost" hint="rate × expected late hours" cells={cell((s) => rs(s.metrics!.sla_cost))} />
                  <Row label="Stock-out cost" hint="rate × expected stock-out hours" cells={cell((s) => rs(s.metrics!.stockout_cost))} />
                  <Row label="Expected total" cells={cell((s) => <strong>{rs(s.metrics!.total)}</strong>)} />
                  <tr>
                    <th scope="row" className="!normal-case !text-sm !font-medium !text-slate-700">Notes</th>
                    {cols.map((s) => (
                      <td key={s.code} className="text-xs">
                        {!s.eligible && <span className="text-slate-600">{s.ineligible_reason}</span>}
                        {s.violations.map((v) => <div key={v.constraint} className="text-red-800">✕ {v.text}</div>)}
                        {s.metrics?.lots && s.metrics.lots.length > 1 && s.metrics.lots.map((l) => <div key={l.lot_type}>{l.lot_type.toLowerCase()} {l.quantity_t} t: P50 {fmtEta(l.p50_at)}, P(late) {pct(l.p_late)}</div>)}
                      </td>
                    ))}
                  </tr>
                  {open && (
                    <tr>
                      <th scope="row" className="!normal-case !text-sm !font-medium !text-slate-700">Decision</th>
                      {cols.map((s) => {
                        const needs = !s.feasible || rec.option_code !== s.code
                        return <td key={s.code}>{s.eligible && <button className={needs ? 'btn-secondary' : 'btn-primary'} disabled={busy || running || (needs && reason.trim().length < 5)} onClick={() => approve(s)}>{needs ? `Override: approve ${NAME[s.code]}` : `Approve ${NAME[s.code]}`}</button>}</td>
                      })}
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            {open && (
              <div className="mt-3 grid md:grid-cols-3 gap-3 items-end">
                <label className="md:col-span-2 text-sm">Reason (required to approve anything other than the recommended feasible option; logged as CONSTRAINT OVERRIDE)
                  <textarea className="input mt-1" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <button className="btn-secondary" onClick={reject} disabled={busy}>Reject case (change nothing)</button>
              </div>
            )}
            <p className="text-xs text-slate-500 mt-3">Costs are incremental versus the current plan and use fictional rates: SLA {rs(kase.context.sla_penalty_per_late_hour as number)} per late hour, stock-out {rs(kase.context.stockout_cost_per_hour_rs as number)} per hour. Hard constraints: max P(stock-out) {pct(kase.constraints.alpha as number)}{kase.constraints.max_freight_rs != null ? `, max extra freight ${rs(kase.constraints.max_freight_rs as number)}` : ''}{kase.constraints.beta != null ? `, max P(late) ${pct(kase.constraints.beta as number)}` : ''}. Simulated at {fmtTime(kase.created_sim_at)}.</p>
          </Card>

          {kase.stability && (
            <Card title="How stable is this recommendation?" right={<span className={`rounded px-2 py-0.5 text-xs font-bold ${kase.stability.label === 'STABLE' ? 'bg-green-700 text-white' : kase.stability.label === 'SENSITIVE' ? 'bg-amber-500 text-black' : 'bg-red-700 text-white'}`}>{kase.stability.label}</span>}>
              <p className="text-sm">The recommendation <strong>holds in {kase.stability.holds} of {kase.stability.total} stress cases</strong> (a count, not a probability). Each case moves freight cost, SLA rate, stock-out rate and disruption duration by −25% or +25%.</p>
              {kase.stability.break_even && <p className="text-sm mt-1">Nearest break-even against Continue: {kase.stability.break_even.nearest.replace('_', ' ')} × {kase.stability.break_even.nearest_multiplier.toFixed(1)} (cost ordering only).</p>}
              <button className="text-sm underline text-navy-700 mt-2" onClick={() => setShowCases(!showCases)} aria-expanded={showCases}>{showCases ? 'Hide' : 'Show'} the 16 cases</button>
              {showCases && (
                <div className="overflow-x-auto mt-2">
                  <table className="w-full">
                    <thead><tr className="border-b border-slate-200"><th>Freight</th><th>SLA rate</th><th>Stock-out rate</th><th>Duration</th><th>Result</th><th>Same?</th></tr></thead>
                    <tbody>{kase.stability.cases.map((x, i) => (
                      <tr key={i} className="border-b border-slate-100">
                        {[x.freight, x.sla_rate, x.stockout_rate, x.duration].map((v, j) => <td key={j}>{v < 1 ? '−25%' : '+25%'}</td>)}
                        <td>{x.recommendation.replace(/_/g, ' ')}</td><td>{x.same ? '✓ same' : '✕ changed'}</td>
                      </tr>
                    ))}</tbody>
                  </table>
                </div>
              )}
            </Card>
          )}
        </>
      )}
    </div>
  )
}
