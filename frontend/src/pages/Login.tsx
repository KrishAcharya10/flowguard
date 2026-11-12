import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setSession, type User } from '../api/client'
import { Notice } from '../components/ui'

const ROLES = [
  { key: 'coordinator', title: 'Logistics coordinator', text: 'See every shipment, get warned early, decide.' },
  { key: 'customer_a', title: 'Customer', text: 'Where is my order, and will it arrive on time?' },
  { key: 'driver1', title: 'Transporter / driver', text: 'Update status as the truck moves.' },
]

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
    <div className="min-h-screen bg-navy-900 flex items-center justify-center p-4">
      <div className="w-full max-w-3xl grid md:grid-cols-2 gap-6">
        <div className="text-white">
          <h1 className="text-4xl font-bold">FlowGuard</h1>
          <p className="text-slate-200 mt-1">Predict. Simulate. Deliver.</p>
          <p className="text-slate-300 text-sm mt-4">Order-to-Delivery Control Tower for the fictional Plant X. Tracking tells you where the truck is. FlowGuard tells you whether it matters and what to do.</p>
          <p className="label !text-slate-400 mt-6 mb-2">Choose a role (fills the username)</p>
          <div className="space-y-2">
            {ROLES.map((r) => (
              <button key={r.key} type="button" onClick={() => setUsername(r.key)}
                className={`w-full text-left rounded-md border px-3 py-2 ${username === r.key ? 'bg-white text-navy-900 border-white' : 'border-white/30 text-white hover:bg-navy-800'}`}>
                <div className="font-semibold text-sm">{r.title} <span className="font-normal opacity-70">· {r.key}</span></div>
                <div className="text-xs opacity-80">{r.text}</div>
              </button>
            ))}
          </div>
        </div>
        <form onSubmit={submit} className="card p-6 self-center">
          <h2 className="text-lg font-bold text-navy-900 mb-4">Sign in</h2>
          <label className="block mb-3"><span className="label">Username</span>
            <input className="input mt-1" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required maxLength={64} />
          </label>
          <label className="block mb-4"><span className="label">Password</span>
            <input className="input mt-1" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required maxLength={128} />
          </label>
          {error && <div className="mb-3"><Notice kind="error">{error}</Notice></div>}
          <button className="btn-primary w-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <p className="text-xs text-navy-900 mt-4 rounded bg-navy-50 border border-navy-100 p-2"><strong>Presenting?</strong> Log in as <strong>coordinator</strong> and open <strong>Demo guide</strong> in the top menu: 8 ready-made use cases with one-click setup and step-by-step instructions.</p>
          <p className="text-xs text-slate-500 mt-2">Fictional demo accounts only. Credentials are listed in the README. Each browser tab keeps its own login.</p>
        </form>
      </div>
    </div>
  )
}
