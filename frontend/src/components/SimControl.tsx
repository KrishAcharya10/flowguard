// Simulation control: start / pause the clock, choose the speed, advance by hand, reset the demo data.
// Everything goes through the real backend clock; nothing here is browser-only state.
import { useState } from 'react'
import { api, refreshAll, useApi, type Clock } from '../api/client'
import { fmtTime } from '../lib/format'
import Icon from './Icons'
import { Notice } from './ui'

const SPEEDS = [1, 5, 15, 30]

export default function SimControl({ demoMode }: { demoMode: boolean }) {
  const { data: clock } = useApi<Clock>('/api/simulation/clock')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error' | 'warn'; text: string } | null>(null)
  if (!clock) return null
  const running = !clock.paused

  const run = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true)
    setMsg(null)
    try { await fn(); if (ok) setMsg({ kind: 'ok', text: ok }); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  const control = (body: object, ok?: string) => run(() => api('/api/simulation/clock/control', { method: 'POST', body }), ok)
  const advance = (minutes: number) => run(() => api('/api/simulation/clock/advance', { method: 'POST', body: { minutes } }), `Clock advanced ${minutes >= 60 ? `${minutes / 60} h` : `${minutes} min`}.`)
  const reset = () => { if (window.confirm('Reset all demo data to the seeded starting state?')) run(() => api('/api/admin/reset', { method: 'POST' }), 'Demo data reset.') }

  return (
    <section className="rounded-xl border border-navy-800/20 bg-gradient-to-r from-navy-900 to-navy-800 text-white p-4 shadow-sm" aria-label="Simulation control">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-3">
        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold">Simulation control</div>
          <div className="text-2xl font-bold leading-tight" data-testid="sim-time">{fmtTime(clock.sim_now)}</div>
          <div className={`text-xs font-bold ${running ? 'text-emerald-300' : 'text-amber-300'}`} data-testid="sim-status">
            {running ? <><span className="inline-block h-2 w-2 rounded-full bg-emerald-400 animate-pulse mr-1" />RUNNING · {clock.speed} simulated min per second</> : '❚❚ PAUSED'}
          </div>
        </div>

        <button className={`btn !px-5 !py-2.5 !text-base ${running ? 'bg-amber-500 border-amber-500 text-black hover:bg-amber-400' : 'bg-emerald-500 border-emerald-500 text-black hover:bg-emerald-400'}`}
          disabled={busy || !demoMode} onClick={() => control({ paused: running }, running ? 'Simulation paused.' : 'Simulation running. Open War Room cases go out of date while time moves.')}>
          <Icon name={running ? 'pause' : 'play'} size={16} />{running ? 'Pause' : 'Start'}
        </button>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold mb-1">Speed (simulated minutes per second)</div>
          <div className="inline-flex rounded-lg overflow-hidden border border-white/30" role="group" aria-label="Simulation speed">
            {SPEEDS.map((sp) => (
              <button key={sp} disabled={busy} aria-pressed={clock.speed === sp} onClick={() => control({ speed: sp })}
                className={`px-3 py-1.5 text-sm font-semibold ${clock.speed === sp ? 'bg-white text-navy-900' : 'text-white hover:bg-white/10'}`}>{sp}×</button>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[11px] uppercase tracking-wide text-slate-300 font-semibold mb-1">Advance by hand</div>
          <div className="flex gap-1.5">
            {[15, 60, 240].map((mnt) => (
              <button key={mnt} className="btn border-white/30 text-white hover:bg-white/10 !py-1.5" disabled={busy || running} onClick={() => advance(mnt)}>
                +{mnt >= 60 ? `${mnt / 60} h` : `${mnt} min`}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto flex flex-col gap-1.5 items-start">
          <label className="text-xs flex items-center gap-1.5 text-slate-200">
            <input type="checkbox" checked={clock.pause_on_alert} onChange={(e) => control({ pause_on_alert: e.target.checked })} />
            Pause automatically on a new high-risk alert
          </label>
          {demoMode && <button className="btn border-white/30 text-white hover:bg-white/10 !py-1" disabled={busy} onClick={reset}><Icon name="reset" size={14} />Reset demo data</button>}
        </div>
      </div>
      <p className="text-[11px] text-slate-300 mt-2">Time never moves by itself unless you press Start. Events are processed in order from the fixed seed, so a run is repeatable. Pause before approving in the War Room.</p>
      {msg && <div className="mt-2 text-slate-900"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </section>
  )
}
