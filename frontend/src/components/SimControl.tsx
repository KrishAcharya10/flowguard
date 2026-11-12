// Compact simulation toolbar: one slim row. Start / pause the clock, speed, advance by hand, reset the demo data.
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
  const seg = 'inline-flex rounded-md overflow-hidden border border-white/25'

  return (
    <section className="rounded-lg bg-navy-900 text-white px-4 py-2.5 shadow-card" aria-label="Simulation control">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-3 min-w-0">
          <span className={`h-2.5 w-2.5 rounded-full shrink-0 ${running ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} aria-hidden />
          <div>
            <div className="text-[17px] font-bold leading-tight tabular-nums" data-testid="sim-time">{fmtTime(clock.sim_now)}</div>
            <div className={`text-[11px] font-bold tracking-wide ${running ? 'text-emerald-300' : 'text-amber-300'}`} data-testid="sim-status">
              {running ? `RUNNING · ${clock.speed} sim min/s` : 'PAUSED'}
            </div>
          </div>
        </div>

        <button className={`btn !px-4 ${running ? 'bg-amber-400 border-amber-400 text-slate-900 hover:bg-amber-300' : 'bg-emerald-500 border-emerald-500 text-slate-900 hover:bg-emerald-400'}`}
          disabled={busy || !demoMode} onClick={() => control({ paused: running }, running ? 'Simulation paused.' : 'Simulation running. Open War Room cases go out of date while time moves.')}>
          <Icon name={running ? 'pause' : 'play'} size={14} />{running ? 'Pause' : 'Start'}
        </button>

        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-slate-300 font-semibold">Speed</span>
          <div className={seg} role="group" aria-label="Simulation speed (simulated minutes per second)">
            {SPEEDS.map((sp) => (
              <button key={sp} disabled={busy} aria-pressed={clock.speed === sp} onClick={() => control({ speed: sp })} title={`${sp} simulated minute${sp > 1 ? 's' : ''} per real second`}
                className={`px-2.5 py-1 text-[13px] font-semibold transition-colors ${clock.speed === sp ? 'bg-white text-navy-900' : 'text-white hover:bg-white/10'}`}>{sp}×</button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wider text-slate-300 font-semibold">Advance</span>
          <div className={seg} role="group" aria-label="Advance the clock by hand">
            {[15, 60, 240].map((mnt) => (
              <button key={mnt} className="px-2.5 py-1 text-[13px] font-semibold text-white hover:bg-white/10 disabled:opacity-40 border-l border-white/20 first:border-l-0" disabled={busy || running} onClick={() => advance(mnt)}>
                +{mnt >= 60 ? `${mnt / 60} h` : `${mnt} min`}
              </button>
            ))}
          </div>
        </div>

        <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <label className="text-[12px] flex items-center gap-1.5 text-slate-200" title="Time never moves by itself unless you press Start. Pause before approving in the War Room.">
            <input type="checkbox" checked={clock.pause_on_alert} onChange={(e) => control({ pause_on_alert: e.target.checked })} />
            Auto-pause on a new high-risk alert
          </label>
          {demoMode && <button className="btn border-white/30 text-white hover:bg-white/10 !py-1 !text-xs" disabled={busy} onClick={reset}><Icon name="reset" size={13} />Reset demo</button>}
        </div>
      </div>
      {msg && <div className="mt-2 text-slate-900"><Notice kind={msg.kind}>{msg.text}</Notice></div>}
    </section>
  )
}
