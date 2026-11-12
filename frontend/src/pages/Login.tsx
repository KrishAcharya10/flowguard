import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setSession, type User } from '../api/client'
import Icon from '../components/Icons'
import { Notice } from '../components/ui'

const ROLES = [
  { key: 'coordinator', icon: 'grid', title: 'Logistics coordinator', text: 'See every shipment, get warned early, decide.' },
  { key: 'customer_a', icon: 'box', title: 'Customer', text: 'Where is my order, and will it arrive on time?' },
  { key: 'driver1', icon: 'truck', title: 'Transporter / driver', text: 'Update status as the truck moves.' },
]

/** Decorative route network (not real geography): plant at the centre, four routes out, one bypass. */
function Network() {
  return (
    <svg className="absolute inset-0 h-full w-full opacity-45" viewBox="0 0 600 700" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g fill="none" stroke="#5eead4" strokeOpacity="0.28" strokeWidth="2" strokeLinecap="round">
        <path d="M250 380 L270 250 L330 170 L420 90" />
        <path d="M250 380 L360 360 L470 330 L560 300" />
        <path d="M250 380 L215 470 L190 560 L170 650" />
        <path d="M250 380 L150 395 L70 420" />
        <path d="M270 250 L370 235 L400 150 L420 90" strokeDasharray="6 8" stroke="#a78bfa" />
      </g>
      <g fill="#0b1f3a" stroke="#5eead4" strokeOpacity="0.55" strokeWidth="2">
        {[[270, 250], [360, 360], [215, 470], [150, 395], [330, 170], [470, 330], [190, 560]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="5" />)}
        {[[420, 90], [560, 300], [170, 650], [70, 420]].map(([x, y]) => <circle key={`${x}${y}`} cx={x} cy={y} r="9" fill="#0d9488" fillOpacity="0.5" />)}
        <rect x="236" y="366" width="28" height="28" rx="6" fill="#14b8a6" fillOpacity="0.9" stroke="#fff" strokeOpacity="0.7" />
      </g>
    </svg>
  )
}

export default function Login() {
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api<{ access_token: string; user: User }>('/api/auth/login', { method: 'POST', body: { username, password } })
      setSession({ token: r.access_token, user: r.user })
      nav('/')
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)] bg-slate-100">
      <section className="relative overflow-hidden bg-navy-950 text-white px-6 py-10 sm:px-12 lg:px-16 flex flex-col justify-center" aria-label="About FlowGuard">
        <Network />
        <div className="relative max-w-xl">
          <div className="flex items-center gap-3">
            <span className="h-11 w-11 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center"><Icon name="shield" size={24} /></span>
            <span className="text-[30px] font-bold tracking-tight text-white">FlowGuard</span>
          </div>
          <p className="mt-4 text-[22px] font-semibold text-brand-500 leading-snug">Predict. Simulate. Deliver.</p>
          <p className="mt-3 text-[15px] text-slate-300 leading-relaxed">Order-to-Delivery Control Tower for the fictional Plant X. Tracking tells you where the truck is. FlowGuard tells you whether it matters and what to do.</p>
          <div className="mt-8 label !text-slate-400 mb-2">Choose a role (fills the username)</div>
          <div className="space-y-2">
            {ROLES.map((r) => (
              <button key={r.key} type="button" onClick={() => setUsername(r.key)} aria-pressed={username === r.key}
                className={`w-full text-left rounded-lg border px-3.5 py-2.5 flex items-center gap-3 transition-colors ${username === r.key ? 'bg-white text-navy-900 border-white' : 'border-white/15 bg-[#0e2038] text-white hover:bg-[#13294a]'}`}>
                <span className={`h-9 w-9 rounded-md flex items-center justify-center shrink-0 ${username === r.key ? 'bg-navy-900 text-white' : 'bg-white/10'}`}><Icon name={r.icon} size={18} /></span>
                <span><span className="block font-semibold text-sm">{r.title} <span className="font-normal opacity-60">· {r.key}</span></span><span className="block text-xs opacity-75">{r.text}</span></span>
              </button>
            ))}
          </div>
        </div>
      </section>

      <section className="flex items-center justify-center p-6 sm:p-10">
        <form onSubmit={submit} className="card w-full max-w-sm p-7 shadow-pop">
          <h2 className="text-xl font-bold text-navy-900">Sign in</h2>
          <p className="text-[13px] text-slate-500 mt-0.5 mb-5">Use a demo account. The password is the same for every account.</p>
          <label className="block mb-3"><span className="label">Username</span>
            <input className="input mt-1 !py-2" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required maxLength={64} />
          </label>
          <label className="block mb-4"><span className="label">Password</span>
            <input className="input mt-1 !py-2" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required maxLength={128} />
          </label>
          {error && <div className="mb-3"><Notice kind="error">{error}</Notice></div>}
          <button className="btn-primary w-full !py-2.5 !text-sm" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="text-xs text-navy-900 mt-5 rounded-md bg-brand-50 border border-brand-100 p-2.5"><strong>Presenting?</strong> Log in as <strong>coordinator</strong> and open <strong>Demo guide</strong> in the menu: 8 ready-made stories with one-click setup and step-by-step instructions.</p>
          <p className="text-xs text-slate-500 mt-2">Fictional demo accounts only. Credentials are listed in the README. Each browser tab keeps its own login.</p>
        </form>
      </section>
    </div>
  )
}
