// Demo guide: ready-made use cases for presenting FlowGuard to judges.
// Each use case: story, what it proves, which windows to open, step-by-step instructions with links,
// and one-click setup ("start from the beginning" or "jump to the decision point").
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, refreshAll, useApi } from '../api/client'
import { Card, Notice, State } from '../components/ui'
import { getDemo, setDemo, TAB_STYLE, toggleStep, useDemo, type DemoGuide as DG, type UseCase } from '../lib/demo'

function Steps({ uc, active }: { uc: UseCase; active: boolean }) {
  const demo = useDemo()
  const nav = useNavigate()
  return (
    <ol className="space-y-2">
      {uc.steps.map((s, i) => {
        const done = active && !!demo?.done.includes(i)
        return (
          <li key={i} className={`rounded-md border p-3 flex gap-3 ${done ? 'bg-green-50 border-green-200' : 'bg-white border-slate-200'}`}>
            {active
              ? <input type="checkbox" className="mt-1 h-4 w-4" checked={done} onChange={() => toggleStep(i)} aria-label={`Step ${i + 1} done`} />
              : <span className="font-bold text-slate-400 w-4">{i + 1}</span>}
            <div className="flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`text-[11px] font-bold rounded px-1.5 py-0.5 ${TAB_STYLE[s.tab] ?? 'bg-slate-600 text-white'}`}>{s.tab} window</span>
                {s.auto && <span className="text-[11px] rounded bg-violet-100 text-violet-900 border border-violet-300 px-1.5 py-0.5">done for you by “Jump”</span>}
              </div>
              <div className="text-sm font-semibold mt-1">{s.do}</div>
              {s.see && <div className="text-sm text-slate-700 mt-0.5"><span className="text-slate-500">You should see: </span>{s.see}</div>}
            </div>
            {s.link && s.tab === 'Coordinator' && <button className="btn-secondary self-start" onClick={() => nav(s.link)}>Go</button>}
          </li>
        )
      })}
    </ol>
  )
}

export default function DemoGuide() {
  const { data, error, loading, reload } = useApi<DG>('/api/demo/use-cases')
  const demo = useDemo()
  const nav = useNavigate()
  const [selected, setSelected] = useState<string>(getDemo()?.code ?? 'flood-reroute')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)

  if (!data) return <State loading={loading} error={error} onRetry={reload} />
  const uc = data.use_cases.find((u) => u.code === selected) ?? data.use_cases[0]
  const active = demo?.code === uc.code

  const setup = async (mode: 'start' | 'jump') => {
    setBusy(true)
    setMsg(null)
    try {
      const r = await api<{ message: string }>(`/api/demo/use-cases/${uc.code}/setup`, { method: 'POST', body: { mode } })
      // Jump lands on the decision point: every step up to the last automatic one is behind us.
      const lastAuto = uc.steps.reduce((acc, s, i) => (s.auto ? i : acc), -1)
      const done = mode === 'jump' ? uc.steps.map((_, i) => i).filter((i) => i <= lastAuto) : []
      setDemo({ code: uc.code, done, collapsed: false })
      setMsg({ kind: 'ok', text: `${r.message} Other windows: just refresh (logins stay valid).` })
      refreshAll()
    } catch (e) {
      setMsg({ kind: 'error', text: (e as Error).message })
    } finally {
      setBusy(false)
    }
  }
  const firstOpen = uc.steps.findIndex((s, i) => s.tab === 'Coordinator' && !(active && demo?.done.includes(i)))

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold text-navy-900">Demo guide</h1>
        <p className="text-sm text-slate-600">Eight ready-made use cases. Pick one, press <strong>Start</strong> (you do every step live) or <strong>Jump to the decision</strong> (the setup steps are done for you). A presenter panel then follows you on every page. {data.password_hint}.</p>
      </div>
      {!data.demo_mode && <Notice kind="warn">DEMO_MODE is off: setup buttons are disabled.</Notice>}

      <div className="grid lg:grid-cols-3 gap-4">
        <div className="space-y-2" role="list" aria-label="Use cases">
          {data.use_cases.map((u) => (
            <button key={u.code} role="listitem" onClick={() => { setSelected(u.code); setMsg(null) }}
              className={`w-full text-left rounded-lg border p-3 ${u.code === uc.code ? 'border-navy-800 bg-white shadow' : 'border-slate-200 bg-white/70 hover:bg-white'}`}>
              <div className="flex items-center gap-2">
                <span className="h-6 w-6 rounded-full bg-navy-800 text-white text-xs font-bold flex items-center justify-center">{u.number}</span>
                <span className="font-semibold text-sm text-navy-900">{u.title}</span>
              </div>
              <div className="text-xs text-slate-600 mt-1">{u.tagline}</div>
              <div className="flex flex-wrap gap-1 mt-1">{u.proves.map((p) => <span key={p} className="text-[10px] rounded border border-slate-300 px-1">{p}</span>)}
                {demo?.code === u.code && <span className="text-[10px] rounded bg-green-700 text-white px-1">ACTIVE</span>}</div>
            </button>
          ))}
        </div>

        <div className="lg:col-span-2 space-y-4">
          <Card title={`Use case ${uc.number}: ${uc.title}`}>
            <p className="text-sm">{uc.story}</p>
            <div className="grid sm:grid-cols-2 gap-3 mt-3 text-sm">
              <div><div className="label mb-1">Proves</div>{uc.proves.join(' · ')}</div>
              <div><div className="label mb-1">Open these windows (one login each)</div>
                <ul className="list-disc pl-5">{uc.tabs.map((t) => <li key={t}>{t}</li>)}</ul></div>
            </div>
            <div className="flex flex-wrap gap-2 mt-4">
              <button className="btn-secondary" disabled={busy || !data.demo_mode} onClick={() => setup('start')}>▶ Start from the beginning</button>
              <button className="btn-primary" disabled={busy || !data.demo_mode} onClick={() => setup('jump')}>⏩ Jump to the decision point</button>
              {active && firstOpen >= 0 && uc.steps[firstOpen].link && <button className="btn-secondary" onClick={() => nav(uc.steps[firstOpen].link)}>Go to next coordinator step →</button>}
              {active && <button className="btn-secondary" onClick={() => setDemo(null)}>Stop guiding</button>}
            </div>
            <p className="text-xs text-slate-500 mt-2">Both buttons first reset all demo data to the seeded start. Setup changes are made through the normal services and appear in the audit trail.</p>
            {msg && <div className="mt-3"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
          </Card>
          <Card title={active ? 'Steps (tick them off as you go)' : 'Steps'}>
            <Steps uc={uc} active={active} />
            <div className="mt-3 rounded-md bg-navy-50 border border-navy-100 p-3 text-sm"><span className="font-semibold">Say to the judges: </span>{uc.takeaway}</div>
          </Card>
        </div>
      </div>
    </div>
  )
}
