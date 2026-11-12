// Analytics: performance (O5), business impact, intervention history, assumptions, audit, responsible AI.
// Every number comes from the API; nothing here is decorative.
import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, refreshAll, useApi, type AnalyticsOverview, type Assumptions, type AssumptionsOut, type AuditRow, type BusinessImpact, type CaseOut, type DelayCauses, type DimensionRow } from '../api/client'
import { Card, Kpi, Modelled, Notice, State } from '../components/ui'
import { fmtTime, rs } from '../lib/format'

const CAUSES = ['FLOODING', 'BREAKDOWN', 'GATE_CONGESTION', 'SLOW_LOADING', 'LATE_DISPATCH', 'ROUTE_CONGESTION']
const CAUSE_COLOR: Record<string, string> = { FLOODING: '#1d4ed8', BREAKDOWN: '#b91c1c', GATE_CONGESTION: '#b45309', SLOW_LOADING: '#7c3aed', LATE_DISPATCH: '#0f766e', ROUTE_CONGESTION: '#475569' }
const nice = (s: string) => s.replace(/_/g, ' ').toLowerCase().replace(/^./, (c) => c.toUpperCase())
const short = (s: string) => s.replace(' (fictional)', '')

function Performance() {
  const ov = useApi<AnalyticsOverview>('/api/analytics/overview')
  const routes = useApi<DimensionRow[]>('/api/analytics/routes')
  const trans = useApi<DimensionRow[]>('/api/analytics/transporters')
  const causes = useApi<DelayCauses>('/api/analytics/delay-causes')
  const pivot = (rows: DelayCauses['by_route']) => {
    const m = new Map<string, Record<string, number | string>>()
    rows.forEach((r) => { const o = m.get(r.id) ?? { name: short(r.name) }; o[r.cause] = r.attributed_hours; m.set(r.id, o) })
    return [...m.values()]
  }
  const table = (title: string, rows: DimensionRow[] | null) => (
    <Card title={title}>
      <State loading={!rows} empty={!!rows && rows.length === 0} />
      {rows && rows.length > 0 && (
        <>
          <div style={{ height: 180 }}>
            <ResponsiveContainer>
              <BarChart data={rows.map((r) => ({ name: short(r.name), 'On-time %': r.on_time_pct }))} margin={{ top: 20, right: 10, left: -15, bottom: 0 }}>
                <CartesianGrid stroke="#e2e8f0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis domain={[0, 100]} tick={{ fontSize: 11 }} unit="%" />
                <Tooltip /><Bar dataKey="On-time %" fill="#12305a" isAnimationActive={false} label={{ position: 'top', fontSize: 11 }} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <table className="w-full mt-2">
            <thead><tr className="border-b border-slate-200"><th>Name</th><th>Orders</th><th>On time</th><th>On-time %</th><th>Avg delay (late)</th><th>Delay hours</th></tr></thead>
            <tbody>{rows.map((r) => <tr key={r.id} className="border-b border-slate-100"><td>{short(r.name)}</td><td>{r.orders_completed}</td><td>{r.orders_on_time}</td><td className="font-semibold">{r.on_time_pct ?? 'n/a'}%</td><td>{r.average_delay_hours_late_orders ?? '-'} h</td><td>{r.attributed_delay_hours}</td></tr>)}</tbody>
          </table>
        </>
      )}
    </Card>
  )
  const stacked = (title: string, rows?: DelayCauses['by_route']) => (
    <Card title={title}>
      <State loading={!rows} empty={!!rows && rows.length === 0} emptyText="No delay events." />
      {rows && rows.length > 0 && (
        <div style={{ height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={pivot(rows)} margin={{ top: 5, right: 10, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="#e2e8f0" /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} unit=" h" />
              <Tooltip formatter={(v: number, n: string) => [`${v} h`, nice(n)]} /><Legend formatter={(v) => nice(String(v))} wrapperStyle={{ fontSize: 11 }} />
              {CAUSES.map((c) => <Bar key={c} dataKey={c} stackId="a" fill={CAUSE_COLOR[c]} isAnimationActive={false} />)}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
  return (
    <div className="space-y-4">
      <State loading={ov.loading && !ov.data} error={ov.error || routes.error || trans.error || causes.error} onRetry={refreshAll} />
      {ov.data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Kpi label="On-time performance" value={`${ov.data.on_time_pct ?? 'n/a'}%`} sub={`${ov.data.orders_on_time} of ${ov.data.orders_completed} arrived orders, ${ov.data.window_days} days`} />
          <Kpi label="Average delay (late orders)" value={`${ov.data.average_delay_hours_late_orders ?? 'n/a'} h`} sub="arrival after the promise" />
          <Kpi label="Predicted on-time (active)" value={`${ov.data.predicted_on_time_pct_active ?? 'n/a'}%`} sub="shown separately from arrivals" />
          <Kpi label="Warning lead time" value={ov.data.warning_lead_time_hours == null ? 'N/A' : `${ov.data.warning_lead_time_hours} h`} sub="first High alert before the promise" />
        </div>
      )}
      {ov.data && <p className="text-xs text-slate-500">{ov.data.definition} {ov.data.warning_lead_time_note}</p>}
      <div className="grid lg:grid-cols-2 gap-4">
        {table('On-time performance by route', routes.data)}
        {table('On-time performance by transporter company', trans.data)}
        {stacked('Delay causes by route (attributed hours)', causes.data?.by_route)}
        {stacked('Delay causes by transporter company (attributed hours)', causes.data?.by_transporter)}
      </div>
      {causes.data && (
        <Card title="Delay causes: totals">
          <table className="w-full"><thead><tr className="border-b border-slate-200"><th>Cause</th><th>Shipments affected</th><th>Attributed hours</th></tr></thead>
            <tbody>{[...causes.data.totals].sort((a, b) => b.attributed_hours - a.attributed_hours).map((c) => <tr key={c.cause} className="border-b border-slate-100"><td><span style={{ color: CAUSE_COLOR[c.cause] }}>■</span> {nice(c.cause)}</td><td>{c.shipments_affected}</td><td>{c.attributed_hours}</td></tr>)}</tbody>
          </table>
          <p className="text-xs text-slate-500 mt-2">{causes.data.note} Historical data is fictional and seeded with deliberate patterns.</p>
        </Card>
      )}
    </div>
  )
}

function Impact() {
  const { data, error, loading, reload } = useApi<BusinessImpact>('/api/analytics/business-impact')
  if (!data) return <State loading={loading} error={error} onRetry={reload} />
  const a = data.panel_a as { interventions: { intervention_id: number; shipment_id: string; option: string; modelled_late_hours_avoided: number; modelled_cost_difference_rs: number; incremental_freight_rs: number; is_override: boolean }[]; total_modelled_late_hours_avoided: number; total_modelled_cost_difference_rs: number; total_incremental_freight_rs: number; formulas: string[]; title: string }
  const b = data.panel_b as { inputs: Record<string, number>; affected_shipments: number; mitigated_shipments: number; interventions: number; gross_modelled_benefit_rs: number; intervention_cost_rs: number; net_modelled_benefit_rs: number; break_even_cost_per_late_hour_rs: number; formulas: string[] }
  return (
    <div className="space-y-4">
      <div className="rounded-md bg-slate-800 text-white text-sm font-bold p-3">{data.label}</div>
      <Card title={<>Panel A · {a.title} <Modelled /></>}>
        <div className="grid grid-cols-3 gap-3 mb-3">
          <Kpi label="Modelled late hours avoided" value={`${a.total_modelled_late_hours_avoided.toFixed(1)} h`} />
          <Kpi label="Modelled cost difference" value={rs(a.total_modelled_cost_difference_rs)} sub="Total(Continue) − Total(chosen)" />
          <Kpi label="Extra freight committed" value={rs(a.total_incremental_freight_rs)} sub="shown separately" />
        </div>
        <State empty={a.interventions.length === 0} emptyText="No intervention has been approved yet. Approve one in the War Room to see its modelled benefit here." />
        {a.interventions.length > 0 && (
          <table className="w-full"><thead><tr className="border-b border-slate-200"><th>Case</th><th>Shipment</th><th>Option</th><th>Late hours avoided</th><th>Cost difference</th><th>Extra freight</th></tr></thead>
            <tbody>{a.interventions.map((r) => <tr key={r.intervention_id} className="border-b border-slate-100"><td>#{r.intervention_id}{r.is_override ? ' (override)' : ''}</td><td><Link className="underline" to={`/shipments/${r.shipment_id}`}>{r.shipment_id}</Link></td><td>{r.option}</td><td>{r.modelled_late_hours_avoided.toFixed(2)} h</td><td>{rs(r.modelled_cost_difference_rs)}</td><td>{rs(r.incremental_freight_rs)}</td></tr>)}</tbody>
          </table>
        )}
        <ul className="text-xs text-slate-500 mt-2 list-disc pl-5">{a.formulas.map((f) => <li key={f}>{f}</li>)}</ul>
      </Card>
      <Card title={<>Panel B · Illustrative annual scenario (edit the inputs in the Assumptions tab) <Modelled /></>}>
        <div className="grid md:grid-cols-2 gap-4">
          <table className="w-full"><thead><tr className="border-b border-slate-200"><th>Input (assumption)</th><th>Value</th></tr></thead>
            <tbody>{Object.entries(b.inputs).map(([k, v]) => <tr key={k} className="border-b border-slate-100"><td>{nice(k)}</td><td>{v.toLocaleString('en-IN')}</td></tr>)}</tbody>
          </table>
          <table className="w-full"><thead><tr className="border-b border-slate-200"><th>Result (modelled)</th><th>Value</th></tr></thead>
            <tbody>
              <tr className="border-b border-slate-100"><td>Affected shipments / year</td><td>{Math.round(b.affected_shipments).toLocaleString('en-IN')}</td></tr>
              <tr className="border-b border-slate-100"><td>Mitigated shipments</td><td>{Math.round(b.mitigated_shipments).toLocaleString('en-IN')}</td></tr>
              <tr className="border-b border-slate-100"><td>Interventions needed</td><td>{Math.round(b.interventions).toLocaleString('en-IN')}</td></tr>
              <tr className="border-b border-slate-100"><td>Gross modelled benefit</td><td>{rs(b.gross_modelled_benefit_rs)}</td></tr>
              <tr className="border-b border-slate-100"><td>Intervention cost</td><td>{rs(b.intervention_cost_rs)}</td></tr>
              <tr className="border-b border-slate-100 font-bold"><td>Net modelled benefit</td><td className={b.net_modelled_benefit_rs < 0 ? 'text-red-700' : ''}>{rs(b.net_modelled_benefit_rs)}</td></tr>
              <tr><td>Break-even cost per late hour</td><td>{rs(b.break_even_cost_per_late_hour_rs)}</td></tr>
            </tbody>
          </table>
        </div>
        <ul className="text-xs text-slate-500 mt-3 list-disc pl-5">{b.formulas.map((f) => <li key={f}>{f}</li>)}</ul>
      </Card>
    </div>
  )
}

function History() {
  const { data, error, loading, reload } = useApi<CaseOut[]>('/api/interventions')
  return (
    <Card title="Intervention history (every decision case)">
      <State loading={loading && !data} error={error} empty={!!data && data.length === 0} emptyText="No decision cases yet." onRetry={reload} />
      {data && data.length > 0 && (
        <div className="overflow-x-auto"><table className="w-full">
          <thead><tr className="border-b border-slate-200"><th>Case</th><th>Shipment</th><th>Simulated at</th><th>Recommendation</th><th>Stability</th><th>Status</th><th>Chosen</th><th>Decided by</th></tr></thead>
          <tbody>{data.map((c) => {
            const chosen = c.scenarios.find((s) => s.id === c.selected_scenario_id)
            return (
              <tr key={c.id} className="border-b border-slate-100">
                <td>#{c.id}</td><td><Link className="underline" to={`/shipments/${c.shipment_id}/war-room`}>{c.shipment_id}</Link></td><td className="text-xs">{fmtTime(c.created_sim_at)}</td>
                <td className="text-xs">{nice(c.recommendation.code)}</td><td className="text-xs">{c.stability ? `${c.stability.label} (${c.stability.holds}/16)` : '-'}</td>
                <td className="text-xs font-semibold">{c.status}</td><td className="text-xs">{chosen ? chosen.code : '-'}{c.is_override ? ' · CONSTRAINT OVERRIDE' : ''}</td><td className="text-xs">{c.decided_by_name ?? '-'}</td>
              </tr>
            )
          })}</tbody>
        </table></div>
      )}
    </Card>
  )
}

const GROUPS: { title: string; keys: (keyof Assumptions)[] }[] = [
  { title: 'War Room constraints', keys: ['alpha', 'max_incremental_freight_rs', 'min_urgent_qty_t', 'beta'] },
  { title: 'War Room costs (fictional Rs)', keys: ['stockout_cost_per_hour_rs', 'reroute_fixed_rs', 'second_vehicle_fixed_rs', 'second_vehicle_lead_h', 'split_cover_hours', 'tie_pct', 'tie_min_abs_rs'] },
  { title: 'Risk index', keys: ['w_late', 'w_stock', 'band_medium_from', 'band_high_from', 'alert_expected_wait_h', 'grace_hours'] },
  { title: 'Engine', keys: ['n_samples', 'sigma_route', 'sigma_segment', 'loading_ref_h', 'loading_min_h', 'loading_mode_h', 'loading_max_h', 'gate_min_h', 'gate_mode_h', 'gate_max_h', 'residual_floor_h', 'fresh_minutes', 'stale_minutes'] },
  { title: 'Business impact panel B', keys: ['annual_shipments', 'delay_rate', 'mitigable_share', 'success_rate', 'avoidable_hours', 'cost_per_late_hour_rs', 'avg_intervention_cost_rs'] },
]
const NULLABLE = new Set(['max_incremental_freight_rs', 'beta'])

function AssumptionsPanel() {
  const { data, error, loading, reload } = useApi<AssumptionsOut>('/api/assumptions')
  const [form, setForm] = useState<Record<string, string>>({})
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  useEffect(() => {
    if (data) setForm(Object.fromEntries(Object.entries(data.values).map(([k, v]) => [k, v === null || v === undefined ? '' : String(v)])))
  }, [data?.assumptions_version])      // live refreshes must never overwrite what the user is typing
  const dirty = useMemo(() => !!data && Object.entries(form).some(([k, v]) => v !== (data.values[k as keyof Assumptions] == null ? '' : String(data.values[k as keyof Assumptions]))), [form, data])
  if (!data) return <State loading={loading} error={error} onRetry={reload} />
  const save = async () => {
    setMsg(null)
    const body: Record<string, number | null> = {}
    for (const [k, v] of Object.entries(form)) {
      if (v.trim() === '') { if (NULLABLE.has(k)) body[k] = null; else { setMsg({ kind: 'error', text: `${nice(k)} is required.` }); return } } else if (Number.isNaN(Number(v))) { setMsg({ kind: 'error', text: `${nice(k)} must be a number.` }); return } else body[k] = Number(v)
    }
    try {
      const r = await api<{ assumptions_version: number; predictions_recomputed: number; cases_superseded: number }>('/api/assumptions', { method: 'PUT', body })
      setMsg({ kind: 'ok', text: `Saved as version ${r.assumptions_version}. ${r.predictions_recomputed} predictions recalculated; ${r.cases_superseded} open War Room case(s) superseded.` })
      refreshAll()
    } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) }
  }
  return (
    <Card title={`Editable assumptions (version ${data.assumptions_version})`} right={<button className="btn-primary" onClick={save} disabled={!dirty}>Save and recalculate</button>}>
      <Notice kind="info">{data.note} Saving recalculates every active prediction, supersedes open War Room cases and writes an audit entry.</Notice>
      {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
      {GROUPS.map((g) => (
        <fieldset key={g.title} className="mt-4">
          <legend className="label mb-2">{g.title}</legend>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {g.keys.map((k) => (
              <label key={k} className="text-xs text-slate-700">{nice(k)}{NULLABLE.has(k) ? ' (blank = off)' : ''}
                <input className="input mt-0.5" inputMode="decimal" value={form[k] ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} />
              </label>
            ))}
          </div>
        </fieldset>
      ))}
    </Card>
  )
}

function Audit() {
  const { data, error, loading, reload } = useApi<AuditRow[]>('/api/audit-events?limit=200')
  return (
    <Card title="Audit trail (append-only)">
      <State loading={loading && !data} error={error} empty={!!data && data.length === 0} emptyText="No audit events yet." onRetry={reload} />
      {data && data.length > 0 && (
        <div className="overflow-x-auto"><table className="w-full">
          <thead><tr className="border-b border-slate-200"><th>Simulated time</th><th>Who</th><th>Action</th><th>Entity</th><th>Details</th></tr></thead>
          <tbody>{data.map((a) => (
            <tr key={a.id} className={`border-b border-slate-100 ${a.action === 'CONSTRAINT OVERRIDE' ? 'bg-red-50' : ''}`}>
              <td className="text-xs whitespace-nowrap">{fmtTime(a.sim_time)}</td><td className="text-xs">{a.actor} ({a.actor_role.toLowerCase()})</td>
              <td className="text-xs font-semibold">{a.action}</td><td className="text-xs">{a.entity_type} {a.entity_id}</td>
              <td className="text-[11px] text-slate-600 max-w-md break-words">{a.after ? JSON.stringify(a.after) : ''}</td>
            </tr>
          ))}</tbody>
        </table></div>
      )}
    </Card>
  )
}

function Responsible() {
  const item = (t: string, d: string) => <li><strong>{t}:</strong> {d}</li>
  return (
    <div className="grid md:grid-cols-2 gap-4">
      <Card title="Where AI is used and where it is not">
        <ul className="text-sm space-y-2 list-disc pl-5">
          {item('Runtime generative AI', 'none. No language model runs in this application.')}
          {item('ETA and delay risk', 'a transparent Monte Carlo simulation (500 samples) under declared distributions. Not a trained ML model; no accuracy claim.')}
          {item('Costs, constraints, recommendation, authorisation', 'deterministic business rules that can be read and tested.')}
          {item('Development', 'generative AI assisted with code and documents. See docs/AI_DISCLOSURE.md.')}
        </ul>
      </Card>
      <Card title="Responsible controls">
        <ul className="text-sm space-y-2 list-disc pl-5">
          {item('Confidence', 'every prediction shows a range (P10–P90), a probability and a data-confidence label; stale telemetry widens the range.')}
          {item('Human approval', 'nothing changes a shipment until a coordinator approves. Overrides need a reason and are logged as CONSTRAINT OVERRIDE.')}
          {item('Freshness', 'approval is refused if the shipment, the assumptions or the clock changed after the scenarios were run.')}
          {item('Access', 'three roles; the server re-checks role and ownership on every request; other users\' records return 404.')}
          {item('Privacy', 'customers get separate allow-list responses with no costs, penalties, stock rates or other customers\' data. Stock data is fictional; a real deployment needs customer consent.')}
          {item('Audit', 'append-only log of who did what, with simulated and wall-clock time.')}
          {item('Limitations', 'fictional data, simplified road rules, single-shipment decisions. See docs/KNOWN_LIMITATIONS.md.')}
        </ul>
      </Card>
    </div>
  )
}

const TABS = [['performance', 'Performance'], ['impact', 'Business impact'], ['history', 'Intervention history'], ['assumptions', 'Assumptions'], ['audit', 'Audit trail'], ['responsible', 'Responsible AI']] as const

export default function Analytics() {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('performance')
  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-1 border-b border-slate-300" role="tablist" aria-label="Analytics sections">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? 'border-navy-800 text-navy-900' : 'border-transparent text-slate-500 hover:text-navy-900'}`}>{label}</button>
        ))}
      </div>
      {tab === 'performance' && <Performance />}
      {tab === 'impact' && <Impact />}
      {tab === 'history' && <History />}
      {tab === 'assumptions' && <AssumptionsPanel />}
      {tab === 'audit' && <Audit />}
      {tab === 'responsible' && <Responsible />}
    </div>
  )
}
