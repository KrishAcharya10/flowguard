// War Room: single-shipment decision workspace. Three scenario cards (Continue / Reroute / Split) simulated on the
// same random conditions, the recommendation with its stability, hard-constraint status, and a human approval with
// an audit trail. All numbers come from the backend; the rules are enforced there, not here.
import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, refreshAll, useApi, type CaseOut, type Clock, type Scenario, type ShipmentDetail } from '../api/client'
import Icon from '../components/Icons'
import { Card, Modelled, Notice, RiskBadge, State } from '../components/ui'
import { fmtEta, fmtTime, hrs, pct, rs } from '../lib/format'

const NAME: Record<string, string> = { CONTINUE: 'Continue', REROUTE: 'Reroute', SPLIT: 'Split shipment' }
const BLURB: Record<string, string> = { CONTINUE: 'Keep the current plan', REROUTE: 'Use the alternative road', SPLIT: 'Send an urgent part on a second vehicle' }

function Bar({ value: v, label }: { value: number | null | undefined; label: string }) {
  if (v == null) return <div className="flex items-baseline justify-between"><span className="text-[11px] text-slate-500">{label}</span><span className="text-xs text-slate-400">n/a (no stock data)</span></div>
  const value = v
  const tone = value >= 0.5 ? 'bg-red-600' : value >= 0.2 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div>
      <div className="flex items-baseline justify-between"><span className="text-[11px] text-slate-500">{label}</span><span className="text-[15px] font-bold tabular-nums text-navy-900">{pct(value)}</span></div>
      <div className="h-1.5 rounded-full bg-slate-200 mt-1 overflow-hidden"><div className={`h-1.5 rounded-full ${tone}`} style={{ width: `${Math.round(value * 100)}%` }} /></div>
    </div>
  )
}

function Line({ label, hint, value, strong = false }: { label: string; hint?: string; value: ReactNode; strong?: boolean }) {
  return (
    <div className={`flex items-baseline justify-between gap-3 py-1 ${strong ? 'border-t border-slate-300 mt-1 pt-2' : ''}`}>
      <span className={`text-[12.5px] ${strong ? 'font-bold text-navy-900' : 'text-slate-600'}`}>{label}{hint && <span className="block text-[10.5px] text-slate-400 leading-tight">{hint}</span>}</span>
      <span className={`tabular-nums ${strong ? 'text-lg font-bold text-navy-900' : 'text-[13px] font-semibold text-slate-800'}`}>{value}</span>
    </div>
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
  const totals = cols.filter((s) => s.eligible && s.metrics).map((s) => s.metrics!.total)
  const lowest = totals.length ? Math.min(...totals) : null
  const tone = rec?.code === 'NO_FEASIBLE_OPTION' ? { bar: 'bg-red-700', box: 'border-red-300 bg-red-50', text: 'text-red-900' } : rec?.code === 'NO_JUSTIFIED_INTERVENTION' ? { bar: 'bg-slate-600', box: 'border-slate-300 bg-slate-50', text: 'text-slate-900' } : { bar: 'bg-emerald-600', box: 'border-emerald-300 bg-emerald-50', text: 'text-emerald-950' }
  const st = kase?.stability
  const stTone = st?.label === 'STABLE' ? 'bg-emerald-600 text-white' : st?.label === 'SENSITIVE' ? 'bg-amber-500 text-slate-900' : 'bg-red-700 text-white'
  const d = ship.data

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link to={`/shipments/${id}`} className="text-[13px] text-navy-700 hover:underline inline-flex items-center gap-1"><Icon name="arrow" size={13} className="rotate-180" />{id}</Link>
        <h1 className="text-[22px] font-bold">War Room</h1>
        <span className="chip bg-white border-slate-300 text-slate-600">Single-shipment decision support. Not fleet optimisation.</span>
        <button className="btn-primary ml-auto" onClick={run} disabled={busy || running}><Icon name="activity" size={14} />{kase ? 'Re-run scenarios' : 'Run scenarios'}</button>
      </div>

      {d && (
        <section className="card grid grid-cols-2 md:grid-cols-5 divide-x divide-slate-200 text-sm overflow-hidden" aria-label="Shipment context">
          {[
            ['Customer', d.customer_name.replace(' (fictional)', '')],
            ['Load', `${d.product_code} · ${d.quantity_tonnes} t`],
            ['Status', d.state_label],
            ['Original promise', fmtTime(d.promised_at)],
          ].map(([k, v]) => <div key={k} className="px-4 py-2.5 min-w-0"><div className="label !text-[10.5px]">{k}</div><div className="font-semibold text-navy-900 truncate">{v}</div></div>)}
          <div className="px-4 py-2.5"><div className="label !text-[10.5px]">Current risk</div><div className="mt-0.5"><RiskBadge level={d.prediction?.risk_category} prefix="" /></div></div>
        </section>
      )}

      {running && (
        <Notice kind="warn">
          <div className="flex flex-wrap items-center gap-3"><span><strong>The simulation clock is running.</strong> Scenarios go out of date every time the clock moves, so you can only run or approve them while it is paused.</span>
            <button className="btn-primary" onClick={pauseClock} disabled={busy}>Pause simulation</button></div>
        </Notice>
      )}
      <State loading={c.loading && !kase} error={c.error} onRetry={c.reload} />
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      {!c.loading && !c.error && !kase && <Notice kind="info">No scenarios yet. Press <strong>Run scenarios</strong> to compare Continue, Reroute and Split on the same simulated conditions.</Notice>}

      {kase && rec && (
        <>
          {kase.is_stale && <Notice kind="warn"><strong>These scenarios are out of date</strong> because {kase.stale_reason}. Re-run them before approving.</Notice>}
          {kase.status !== 'AWAITING_APPROVAL' && <Notice kind={kase.status === 'APPLIED' || kase.status === 'COMPLETED' ? 'ok' : 'info'}>Case #{kase.id} is <strong>{kase.status}</strong>{kase.decided_by_name ? ` (by ${kase.decided_by_name} at ${fmtTime(kase.decided_sim_at)})` : ''}.{kase.is_override ? ` CONSTRAINT OVERRIDE - reason: ${kase.override_reason}` : ''}</Notice>}

          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_21rem]">
            <section className={`rounded-lg border ${tone.box} overflow-hidden flex`}>
              <div className={`w-1.5 shrink-0 ${tone.bar}`} />
              <div className="p-4">
                <div className={`text-[11px] font-bold tracking-wider ${tone.text} opacity-80`}>RECOMMENDATION <Modelled /></div>
                <div className={`text-[22px] font-bold leading-tight mt-1 ${tone.text}`}>{rec.banner}</div>
                <ul className={`mt-2 text-[13px] space-y-0.5 list-disc pl-5 ${tone.text}`}>{(rec.explanation ?? []).map((l) => <li key={l}>{l}</li>)}</ul>
              </div>
            </section>
            {st && (
              <section className="card p-4" aria-label="Recommendation stability">
                <div className="flex items-center justify-between"><h2 className="section-title">Is the recommendation stable?</h2><span className={`rounded px-2 py-0.5 text-xs font-bold ${stTone}`}>{st.label}</span></div>
                <p className="text-[13px] mt-1.5">The recommendation <strong>holds in {st.holds} of {st.total} stress cases</strong> <span className="text-slate-500">(a count, not a probability)</span>.</p>
                <div className="grid grid-cols-8 gap-1 mt-2" aria-hidden>{st.cases.map((x, i) => <span key={i} className={`h-2.5 rounded-sm ${x.same ? 'bg-emerald-500' : 'bg-red-500'}`} />)}</div>
                <p className="text-[11px] text-slate-500 mt-1.5">Each case moves freight, SLA rate, stock-out rate and disruption duration by −25% or +25%.</p>
                {st.break_even && <p className="text-[11px] text-slate-600 mt-1">Nearest break-even against Continue: {st.break_even.nearest.replace('_', ' ')} × {st.break_even.nearest_multiplier.toFixed(1)}.</p>}
                <button className="text-xs underline text-navy-700 mt-1.5" onClick={() => setShowCases(!showCases)} aria-expanded={showCases}>{showCases ? 'Hide' : 'Show'} the 16 cases</button>
              </section>
            )}
          </div>

          {showCases && st && (
            <Card title="The 16 stress cases">
              <div className="overflow-x-auto -mx-4 border-t border-slate-200">
                <table className="w-full">
                  <thead><tr className="border-b border-slate-200"><th>Freight</th><th>SLA rate</th><th>Stock-out rate</th><th>Duration</th><th>Result</th><th>Same?</th></tr></thead>
                  <tbody>{st.cases.map((x, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      {[x.freight, x.sla_rate, x.stockout_rate, x.duration].map((v, j) => <td key={j}>{v < 1 ? '−25%' : '+25%'}</td>)}
                      <td>{x.recommendation.replace(/_/g, ' ')}</td><td>{x.same ? '✓ same' : '✕ changed'}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
            </Card>
          )}

          <div>
            <div className="flex items-baseline justify-between mb-2">
              <h2 className="section-title">Scenario comparison <span className="font-normal text-slate-500">· same random conditions for every option</span></h2>
              <span className="text-[11px] text-slate-500">Simulated at {fmtTime(kase.created_sim_at)}</span>
            </div>
            <div className="grid gap-3 md:grid-cols-3">
              {cols.map((s) => {
                const isRec = rec.option_code === s.code && rec.code !== 'NO_FEASIBLE_OPTION'
                const m = s.metrics
                const needs = !s.feasible || rec.option_code !== s.code
                const border = isRec ? 'border-emerald-500 ring-2 ring-emerald-500/30' : s.eligible && !s.feasible ? 'border-red-300' : 'border-slate-200'
                return (
                  <article key={s.code} className={`rounded-lg border bg-white shadow-card flex flex-col ${border} ${!s.eligible ? 'opacity-70' : ''}`} aria-label={`${NAME[s.code]} scenario`}>
                    <header className={`px-4 py-3 border-b border-slate-200 rounded-t-lg ${isRec ? 'bg-emerald-50' : 'bg-slate-50'}`}>
                      <div className="flex items-center justify-between gap-2">
                        <h3 className="text-[15px] font-bold text-navy-900">{NAME[s.code]}</h3>
                        <div className="flex flex-wrap justify-end gap-1">
                          {isRec && <span className="rounded bg-emerald-700 text-white text-[10px] font-bold px-1.5 py-0.5">★ RECOMMENDED</span>}
                          {rec.least_violating_code === s.code && <span className="rounded bg-slate-200 text-slate-800 text-[10px] px-1.5 py-0.5">least-violating (info only)</span>}
                          {s.eligible && (s.feasible ? <span className="rounded bg-emerald-100 text-emerald-900 text-[10px] font-semibold px-1.5 py-0.5">✓ feasible</span> : <span className="rounded bg-red-100 text-red-900 text-[10px] font-semibold px-1.5 py-0.5">✕ violates a constraint</span>)}
                        </div>
                      </div>
                      <p className="text-xs text-slate-600 mt-0.5">{s.eligible ? s.summary : BLURB[s.code]}</p>
                    </header>

                    {!s.eligible || !m ? (
                      <div className="p-4 text-sm text-slate-700 flex-1"><strong className="block mb-1">Not eligible</strong>{s.ineligible_reason}</div>
                    ) : (
                      <div className="p-4 space-y-3 flex-1">
                        <div className="grid grid-cols-2 gap-2">
                          <div className="rounded-md bg-slate-50 border border-slate-200 p-2"><div className="label !text-[10px]">Median arrival (P50)</div><div className="text-[13px] font-bold text-navy-900 tabular-nums leading-snug">{fmtEta(m.p50_at)}</div></div>
                          <div className="rounded-md bg-slate-50 border border-slate-200 p-2"><div className="label !text-[10px]">Late case (P90)</div><div className="text-[13px] font-bold text-navy-900 tabular-nums leading-snug">{fmtEta(m.p90_at)}</div></div>
                        </div>
                        <div className="space-y-2">
                          <Bar value={m.p_late} label="P(late): any lot after the promise" />
                          <Bar value={m.p_stockout} label="P(customer stock-out)" />
                        </div>
                        <div>
                          <Line label="Expected late hours" value={hrs(m.exp_late_h, 2)} />
                          <Line label="Expected stock-out hours" value={hrs(m.exp_stockout_h, 2)} />
                        </div>
                        <div>
                          <div className="label !text-[10px] mb-0.5">Cost <Modelled /></div>
                          <Line label="Extra freight" hint="certain if chosen" value={rs(m.freight)} />
                          <Line label="SLA cost" hint="rate × expected late hours" value={rs(m.sla_cost)} />
                          <Line label="Stock-out cost" hint="rate × expected stock-out hours" value={rs(m.stockout_cost)} />
                          <Line label="Expected total" strong value={<>{rs(m.total)}{lowest !== null && m.total === lowest && <span className="ml-1.5 align-middle rounded bg-emerald-100 text-emerald-900 text-[9px] font-bold px-1 py-0.5">LOWEST</span>}</>} />
                        </div>
                        <div className="rounded-md border border-slate-200 p-2">
                          <div className="label !text-[10px] mb-1">Constraint status</div>
                          {s.violations.length === 0 ? <div className="text-[12px] text-emerald-800 font-semibold">✓ All hard constraints met</div> : s.violations.map((v) => <div key={v.constraint} className="text-[12px] text-red-800">✕ {v.text}</div>)}
                        </div>
                        {m.lots && m.lots.length > 1 && <div className="text-[11.5px] text-slate-600 space-y-0.5">{m.lots.map((l) => <div key={l.lot_type}>{l.lot_type.toLowerCase()} {l.quantity_t} t: P50 {fmtEta(l.p50_at)}, P(late) {pct(l.p_late)}</div>)}</div>}
                      </div>
                    )}

                    {open && s.eligible && (
                      <footer className="p-3 border-t border-slate-200">
                        <button className={`${needs ? 'btn-secondary' : 'btn-primary'} w-full`} disabled={busy || running || (needs && reason.trim().length < 5)} onClick={() => approve(s)}>{needs ? `Override: approve ${NAME[s.code]}` : `Approve ${NAME[s.code]}`}</button>
                      </footer>
                    )}
                  </article>
                )
              })}
            </div>
          </div>

          <Card title="Human approval and audit trail">
            <ol className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[12.5px] mb-3" aria-label="Approval steps">
              {[['Simulated', true], ['Awaiting approval', kase.status === 'AWAITING_APPROVAL'], ['Decided', kase.status !== 'AWAITING_APPROVAL']].map(([l, on], i) => (
                <li key={String(l)} className="flex items-center gap-2"><span className={`h-5 w-5 rounded-full text-[11px] font-bold flex items-center justify-center ${on ? 'bg-navy-800 text-white' : 'bg-slate-200 text-slate-500'}`}>{i + 1}</span><span className={on ? 'font-semibold text-navy-900' : 'text-slate-500'}>{l as string}</span>{i < 2 && <span className="w-6 h-px bg-slate-300" />}</li>
              ))}
            </ol>
            {open ? (
              <div className="grid md:grid-cols-3 gap-3 items-end">
                <label className="md:col-span-2 text-[13px]">Reason (required to approve anything other than the recommended feasible option; logged as CONSTRAINT OVERRIDE)
                  <textarea className="input mt-1" rows={2} maxLength={500} value={reason} onChange={(e) => setReason(e.target.value)} />
                </label>
                <button className="btn-secondary" onClick={reject} disabled={busy}>Reject case (change nothing)</button>
              </div>
            ) : <p className="text-[13px] text-slate-700">{kase.decided_by_name ? `Decided by ${kase.decided_by_name} at ${fmtTime(kase.decided_sim_at)}.` : 'No decision is pending on this case.'}</p>}
            <p className="text-xs text-slate-500 mt-3">Nothing is executed until a coordinator approves it, and every decision is written to the audit trail (<Link className="underline" to="/analytics">Analytics → Audit trail</Link>). Costs are incremental versus the current plan and use fictional rates: SLA {rs(kase.context.sla_penalty_per_late_hour as number)} per late hour, stock-out {rs(kase.context.stockout_cost_per_hour_rs as number)} per hour. Hard constraints: max P(stock-out) {pct(kase.constraints.alpha as number)}{kase.constraints.max_freight_rs != null ? `, max extra freight ${rs(kase.constraints.max_freight_rs as number)}` : ''}{kase.constraints.beta != null ? `, max P(late) ${pct(kase.constraints.beta as number)}` : ''}.</p>
          </Card>
        </>
      )}
    </div>
  )
}
