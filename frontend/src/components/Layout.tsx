import { useEffect, useState, type ReactNode } from 'react'
import { Link, NavLink, useNavigate } from 'react-router-dom'
import { api, getSession, refreshAll, setSession, startLiveSync, useApi, type Alert, type Clock } from '../api/client'
import { fmtTime } from '../lib/format'
import Icon from './Icons'
import LiveBadge from './LiveBadge'
import PresenterPanel from './PresenterPanel'
import { RiskBadge, State } from './ui'

declare const __BUILD_TIME__: string

function AlertsDrawer({ onClose }: { onClose: () => void }) {
  const { data, error, loading, reload } = useApi<Alert[]>('/api/alerts')
  const nav = useNavigate()
  const ack = async (id: number) => { await api(`/api/alerts/${id}/acknowledge`, { method: 'POST' }); refreshAll() }
  return (
    <div className="fixed inset-0 z-[1000] flex justify-end" role="dialog" aria-modal="true" aria-label="Alerts">
      <button className="flex-1 bg-black/30" aria-label="Close alerts" onClick={onClose} />
      <aside className="w-full max-w-md bg-white h-full overflow-y-auto shadow-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-navy-900">Alerts</h2>
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
        <p className="text-xs text-slate-500 mb-3">An alert is a warning with a suggested action. Nothing is executed until a coordinator approves it in the War Room.</p>
        <State loading={loading && !data} error={error} empty={!!data && data.length === 0} emptyText="No alerts." onRetry={reload} />
        <ul className="space-y-3">
          {data?.map((a) => (
            <li key={a.id} className={`rounded-md border p-3 ${a.acknowledged ? 'border-slate-200 bg-slate-50' : 'border-slate-300 bg-white'}`}>
              <div className="flex items-center justify-between gap-2">
                <RiskBadge level={a.severity} prefix="" />
                <span className="text-xs text-slate-500">{fmtTime(a.created_sim_at)}</span>
              </div>
              <div className="font-semibold text-sm mt-1">{a.title}</div>
              <div className="text-sm text-slate-700 mt-1">{a.message}</div>
              {a.suggested_action && <div className="text-sm mt-2 rounded bg-navy-50 border border-navy-100 p-2"><span className="font-semibold">Suggested: </span>{a.suggested_action.replace(/^Suggested action: /, '')}</div>}
              <div className="flex gap-2 mt-2">
                {a.shipment_id && <button className="btn-primary" onClick={() => { onClose(); nav(`/shipments/${a.shipment_id}/war-room`) }}>Open War Room</button>}
                {a.shipment_id && <button className="btn-secondary" onClick={() => { onClose(); nav(`/shipments/${a.shipment_id}`) }}>Shipment</button>}
                {!a.acknowledged ? <button className="btn-secondary" onClick={() => ack(a.id)}>Acknowledge</button> : <span className="text-xs text-slate-500 self-center">✓ Acknowledged</span>}
              </div>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  )
}

const NAV = [
  { to: '/tower', label: 'Control Tower', icon: 'grid' },
  { to: '/analytics', label: 'Analytics', icon: 'chart' },
  { to: '/gate', label: 'Gate slots', icon: 'gate' },
  { to: '/documents', label: 'Documents', icon: 'file' },
  { to: '/demo', label: 'Demo guide', icon: 'book' },
]

function Footer() {
  return (
    <footer className="text-center text-xs text-slate-500 py-3 px-4">
      Hackathon prototype for the fictional Plant X. All data is fictional. ETA and risk come from a transparent simulation with declared
      assumptions, not a trained ML model. A human approves every intervention. · UI build {new Date(__BUILD_TIME__).toLocaleString('en-GB')}
    </footer>
  )
}

export default function Layout({ children }: { children: ReactNode }) {
  const session = getSession()
  const nav = useNavigate()
  const [drawer, setDrawer] = useState(false)
  useEffect(() => startLiveSync(), [])                       // one poller per open tab, every role
  const clock = useApi<Clock>(session ? '/api/simulation/clock' : null)
  const isCoord = session?.user.role === 'COORDINATOR'
  const open = useApi<Alert[]>(isCoord ? '/api/alerts?only_open=true' : null)
  const logout = () => { setSession(null); nav('/login') }
  const role = session?.user.role
  const running = clock.data && !clock.data.paused

  const clockChip = clock.data && (
    <span className="inline-flex items-center gap-1.5 rounded-md bg-navy-800/90 text-white px-2.5 py-1 text-xs" title="All times come from the simulation clock">
      <Icon name="clock" size={14} />
      <span>Simulated time <strong>{fmtTime(clock.data.sim_now)}</strong></span>
      <span className={`font-bold ${running ? 'text-emerald-300' : 'text-amber-300'}`}>{running ? '● running' : '❚❚ paused'}</span>
    </span>
  )

  // ---------------- customer and driver: compact header ----------------
  if (!isCoord) {
    return (
      <div className="min-h-screen flex flex-col bg-slate-50">
        <header className="bg-navy-900 text-white sticky top-0 z-30">
          <div className="max-w-6xl mx-auto px-4 py-2.5 flex items-center gap-3">
            <Link to="/" className="flex items-center gap-2 font-bold text-lg tracking-tight">
              <span className="h-8 w-8 rounded-lg bg-white/10 flex items-center justify-center"><Icon name={role === 'TRANSPORTER' ? 'truck' : 'box'} /></span>
              <span>FlowGuard<span className="block text-[10px] font-normal text-slate-300 -mt-1">{role === 'TRANSPORTER' ? 'Driver app' : 'Delivery tracking'}</span></span>
            </Link>
            <div className="ml-auto flex items-center gap-2">
              <span className="hidden sm:block"><LiveBadge dark /></span>
              {session && <span className="hidden md:block text-sm text-slate-200">{session.user.display_name}</span>}
              {session && <button className="btn border-white/40 text-white hover:bg-navy-700 !py-1" onClick={logout}><Icon name="logout" size={14} />Log out</button>}
            </div>
          </div>
          <div className="sm:hidden px-4 pb-2"><LiveBadge dark /></div>
        </header>
        <main className="flex-1 w-full max-w-6xl mx-auto px-4 py-4">{children}</main>
        <Footer />
      </div>
    )
  }

  // ---------------- coordinator: sidebar ----------------
  const link = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-semibold ${isActive ? 'bg-white text-navy-900' : 'text-slate-200 hover:bg-white/10'}`
  return (
    <div className="min-h-screen flex bg-slate-50">
      <aside className="hidden lg:flex fixed inset-y-0 left-0 w-60 flex-col bg-navy-900 text-white p-4 z-30">
        <Link to="/tower" className="flex items-center gap-2 font-bold text-xl tracking-tight mb-6">
          <span className="h-9 w-9 rounded-xl bg-white/10 flex items-center justify-center"><Icon name="shield" size={20} /></span>
          <span>FlowGuard<span className="block text-[10px] font-normal text-slate-300 -mt-1">Control Tower</span></span>
        </Link>
        <nav className="space-y-1" aria-label="Main">
          {NAV.map((n) => <NavLink key={n.to} to={n.to} className={link}><Icon name={n.icon} />{n.label}</NavLink>)}
        </nav>
        <div className="mt-auto space-y-3">
          {clock.data && (
            <div className="rounded-xl bg-white/10 p-3 text-xs">
              <div className="text-slate-300">Simulated time</div>
              <div className="text-base font-bold">{fmtTime(clock.data.sim_now)}</div>
              <div className={`mt-1 font-semibold ${running ? 'text-emerald-300' : 'text-amber-300'}`}>
                {running ? `● Running · ${clock.data.speed} min/s` : '❚❚ Paused'}
              </div>
            </div>
          )}
          {session && (
            <div className="text-xs text-slate-300">
              <div className="font-semibold text-white truncate">{session.user.display_name}</div>
              <div>Logistics coordinator</div>
            </div>
          )}
          <button className="btn w-full border-white/30 text-white hover:bg-white/10" onClick={logout}><Icon name="logout" size={14} />Log out</button>
        </div>
      </aside>

      <div className="flex-1 lg:ml-60 min-w-0 flex flex-col">
        <header className="sticky top-0 z-20 bg-white/90 backdrop-blur border-b border-slate-200">
          <div className="px-4 py-2 flex flex-wrap items-center gap-2">
            <nav className="flex lg:hidden gap-1" aria-label="Main (mobile)">
              {NAV.map((n) => (
                <NavLink key={n.to} to={n.to} className={({ isActive }) => `px-2.5 py-1.5 rounded-md text-sm font-semibold ${isActive ? 'bg-navy-900 text-white' : 'text-navy-900 hover:bg-slate-100'}`}>{n.label}</NavLink>
              ))}
            </nav>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <span className="hidden md:block">{clockChip}</span>
              <LiveBadge />
              <button className="btn-secondary relative" onClick={() => setDrawer(true)} aria-label={`Open alerts, ${open.data?.length ?? 0} unacknowledged`}>
                <Icon name="bell" size={16} />Alerts
                {open.data && open.data.length > 0 && <span className="ml-1 rounded-full bg-red-700 text-white text-xs px-1.5">{open.data.length}</span>}
              </button>
              <button className="btn-secondary lg:hidden" onClick={logout}>Log out</button>
            </div>
          </div>
        </header>
        <main className="flex-1 px-4 py-4 max-w-[1500px] w-full mx-auto">{children}</main>
        <Footer />
      </div>
      {drawer && <AlertsDrawer onClose={() => setDrawer(false)} />}
      <PresenterPanel />
    </div>
  )
}
