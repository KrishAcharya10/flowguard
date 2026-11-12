// Floating presenter panel: shows the active use case's next steps on every coordinator page.
import { useNavigate } from 'react-router-dom'
import { useApi } from '../api/client'
import { setDemo, TAB_STYLE, toggleStep, useDemo, type DemoGuide } from '../lib/demo'

export default function PresenterPanel() {
  const demo = useDemo()
  const nav = useNavigate()
  const { data } = useApi<DemoGuide>(demo ? '/api/demo/use-cases' : null)
  if (!demo || !data) return null
  const uc = data.use_cases.find((u) => u.code === demo.code)
  if (!uc) return null
  const next = uc.steps.findIndex((_, i) => !demo.done.includes(i))
  const count = demo.done.length

  if (demo.collapsed) {
    return (
      <button className="fixed bottom-4 right-4 z-[900] btn-primary shadow-lg" onClick={() => setDemo({ ...demo, collapsed: false })}>
        Demo: use case {uc.number} · {count}/{uc.steps.length} ▴
      </button>
    )
  }
  return (
    <aside className="fixed bottom-4 right-4 z-[900] w-[360px] max-h-[70vh] flex flex-col rounded-lg border border-navy-800 bg-white shadow-2xl" aria-label="Presenter guide">
      <div className="bg-navy-800 text-white rounded-t-lg px-3 py-2 flex items-center gap-2">
        <div className="flex-1 min-w-0">
          <div className="text-[11px] opacity-80">Presenter guide · use case {uc.number} · {count}/{uc.steps.length} done</div>
          <div className="text-sm font-semibold truncate" title={uc.title}>{uc.title}</div>
        </div>
        <button className="text-xs underline" onClick={() => nav('/demo')}>All</button>
        <button className="text-xs underline" onClick={() => setDemo({ ...demo, collapsed: true })} aria-label="Minimise presenter guide">Hide</button>
        <button className="text-xs underline" onClick={() => setDemo(null)} aria-label="Stop guiding">✕</button>
      </div>
      <ol className="overflow-y-auto p-2 space-y-1.5">
        {uc.steps.map((s, i) => {
          const done = demo.done.includes(i)
          const isNext = i === next
          return (
            <li key={i} className={`rounded border p-2 text-xs flex gap-2 ${isNext ? 'border-navy-800 bg-navy-50' : done ? 'border-green-200 bg-green-50 opacity-70' : 'border-slate-200'}`}>
              <input type="checkbox" className="mt-0.5" checked={done} onChange={() => toggleStep(i)} aria-label={`Step ${i + 1} done`} />
              <div className="flex-1">
                <span className={`font-bold rounded px-1 mr-1 ${TAB_STYLE[s.tab] ?? 'bg-slate-600 text-white'}`}>{s.tab}</span>
                {isNext && <span className="font-bold text-navy-900">NEXT: </span>}
                <span className={done ? 'line-through' : 'font-semibold'}>{s.do}</span>
                {isNext && s.see && <div className="text-slate-600 mt-0.5">See: {s.see}</div>}
                {isNext && s.tab !== 'Coordinator' && <div className="text-amber-800 mt-0.5">→ switch to the {s.tab.toLowerCase()} window</div>}
              </div>
              {isNext && s.link && s.tab === 'Coordinator' && <button className="btn-secondary !px-2 !py-0.5 self-start" onClick={() => nav(s.link)}>Go</button>}
            </li>
          )
        })}
      </ol>
      {next === -1 && <div className="p-2 text-xs bg-green-50 text-green-900 border-t border-green-200 rounded-b-lg">Done. Say: {uc.takeaway}</div>}
    </aside>
  )
}
