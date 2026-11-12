// "Where is my order?" assistant. Deterministic and read-only: every answer is built by the backend from the
// customer's own records. It never guesses, never shows internal costs, and cannot change anything.
import { useEffect, useRef, useState } from 'react'
import { api, downloadDocument, getSession, type ChatReply } from '../api/client'
import { fmtTime } from '../lib/format'
import Icon from './Icons'

interface Msg { id: number; from: 'me' | 'bot'; text: string; wall: string; reply?: ChatReply; error?: boolean }

const wallTime = () => new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
const START: Msg = { id: 0, from: 'bot', wall: '', text: 'Hello! I can tell you where your orders are, when they will arrive, whether they are delayed and why, and whether your invoice and proof of delivery are ready. I only read your own order data, so I never guess.' }
const START_SUGGESTIONS = ['Where is my order?', 'When will my delivery arrive?', 'Has my order been dispatched?', 'Why is my order delayed?']

export default function ChatWidget({ orders, onOpenOrder, onOpenTab }: { orders: { id: string }[]; onOpenOrder: (id: string) => void; onOpenTab: (tab: string) => void }) {
  const key = `flowguard.chat.${getSession()?.user.id ?? 'x'}`
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState<Msg[]>(() => {
    try { const raw = sessionStorage.getItem(key); return raw ? JSON.parse(raw) : [START] } catch { return [START] }
  })
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [about, setAbout] = useState('')
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLInputElement>(null)

  useEffect(() => { try { sessionStorage.setItem(key, JSON.stringify(msgs.slice(-40))) } catch { /* storage unavailable */ } }, [msgs, key])
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy, open])
  useEffect(() => { if (open) box.current?.focus() }, [open])

  const send = async (q: string) => {
    const message = q.trim()
    if (!message || busy) return
    setText('')
    setMsgs((m) => [...m, { id: Date.now(), from: 'me', text: message, wall: wallTime() }])
    setBusy(true)
    try {
      const reply = await api<ChatReply>('/api/customer/me/chat', { method: 'POST', body: { message, order_id: about || null } })
      setMsgs((m) => [...m, { id: Date.now() + 1, from: 'bot', text: reply.text, wall: wallTime(), reply }])
    } catch (e) {
      setMsgs((m) => [...m, { id: Date.now() + 1, from: 'bot', wall: wallTime(), error: true, text: `I could not get that answer (${(e as Error).message}). Please try again.` }])
    } finally { setBusy(false) }
  }
  const lastBot = [...msgs].reverse().find((m) => m.from === 'bot')

  return (
    <>
      {!open && (
        <button onClick={() => setOpen(true)} aria-label="Open the Where is my order chat"
          className="fixed bottom-5 right-5 z-40 flex items-center gap-2.5 rounded-full bg-gradient-to-r from-navy-800 to-sky-700 text-white pl-4 pr-5 py-3 shadow-xl hover:shadow-2xl hover:scale-[1.03] transition">
          <span className="relative"><Icon name="chat" size={22} /><span className="absolute -top-1 -right-1 h-2.5 w-2.5 rounded-full bg-emerald-400 ring-2 ring-navy-800" /></span>
          <span className="font-semibold text-sm">Where is my order?</span>
        </button>
      )}
      {open && (
        <section role="dialog" aria-label="Where is my order assistant" data-testid="chat-panel"
          className="fixed z-50 inset-x-2 bottom-2 top-16 sm:inset-auto sm:bottom-5 sm:right-5 sm:w-[400px] sm:h-[600px] sm:max-h-[88vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
          <header className="bg-gradient-to-r from-navy-900 to-sky-800 text-white px-4 py-3 flex items-center gap-3">
            <span className="h-10 w-10 rounded-full bg-white/15 flex items-center justify-center"><Icon name="truck" size={20} /></span>
            <div className="min-w-0 flex-1"><div className="font-bold leading-tight">Delivery assistant</div><div className="text-[11px] text-slate-200">Answers from your own orders only · no guessing</div></div>
            <button className="rounded-md p-1.5 hover:bg-white/15" onClick={() => setMsgs([START])} aria-label="Start a new conversation" title="Start over"><Icon name="reset" size={16} /></button>
            <button className="rounded-md px-2 py-1 text-sm font-semibold hover:bg-white/15" onClick={() => setOpen(false)} aria-label="Close chat">✕</button>
          </header>

          <div className="px-3 pt-2 pb-1 bg-slate-50 border-b border-slate-200 flex items-center gap-2 text-xs">
            <label htmlFor="chat-about" className="text-slate-600 font-semibold">Ask about</label>
            <select id="chat-about" className="input !py-1 !text-xs" value={about} onChange={(e) => setAbout(e.target.value)}>
              <option value="">All my open orders</option>
              {orders.map((o) => <option key={o.id} value={o.id}>{o.id}</option>)}
            </select>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3 bg-gradient-to-b from-slate-50 to-white" aria-live="polite">
            {msgs.map((m) => (
              <div key={m.id} className={`flex ${m.from === 'me' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[88%] ${m.from === 'me' ? 'items-end' : 'items-start'} flex flex-col gap-1.5`}>
                  <div className={`rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed whitespace-pre-line ${m.from === 'me' ? 'bg-navy-800 text-white rounded-br-md' : m.error ? 'bg-red-50 border border-red-200 text-red-900 rounded-bl-md' : 'bg-white border border-slate-200 shadow-sm text-slate-900 rounded-bl-md'}`}>{m.text}</div>
                  {m.reply && m.reply.facts.length > 0 && (
                    <dl className="w-full rounded-xl bg-sky-50 border border-sky-200 px-3 py-2 text-xs grid grid-cols-[auto,1fr] gap-x-3 gap-y-1">
                      {m.reply.facts.map((f) => <div key={f.label} className="contents"><dt className="font-semibold text-sky-900">{f.label}</dt><dd className="text-slate-800">{f.value}</dd></div>)}
                    </dl>
                  )}
                  {m.reply?.position && (
                    <div className="w-full rounded-xl bg-emerald-50 border border-emerald-200 px-3 py-2 text-xs flex items-start gap-2">
                      <Icon name="map" size={16} className="mt-0.5 text-emerald-800" />
                      <div><div className="font-semibold text-emerald-900">Latest reported position</div>
                        <div>Near {m.reply.position.near} · {m.reply.position.progress_pct}% of the route</div><div className="text-slate-600">Reported {fmtTime(m.reply.position.reported_at)} (simulated)</div></div>
                    </div>
                  )}
                  {m.reply && m.reply.links.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {m.reply.links.map((l, i) => (
                        <button key={i} className="btn-secondary !py-1 !px-2.5 !text-xs !rounded-full" onClick={() => {
                          if (l.kind === 'order' && l.order_id) { onOpenOrder(l.order_id); setOpen(false) }
                          else if (l.kind === 'tab' && l.tab) { onOpenTab(l.tab); setOpen(false) }
                          else if (l.kind === 'document' && l.document_id) void downloadDocument(l.document_id, l.label.replace(/[^\w ()-]/g, '') + '.pdf').catch(() => undefined)
                        }}>
                          <Icon name={l.kind === 'document' ? 'download' : l.kind === 'tab' ? 'bell' : 'box'} size={13} />{l.label}
                        </button>
                      ))}
                    </div>
                  )}
                  <div className="text-[10px] text-slate-400 px-1">{m.from === 'me' ? `You · ${m.wall}` : m.reply ? `Data as of ${fmtTime(m.reply.as_of)} (simulated) · replied ${m.wall}` : m.wall ? `Assistant · ${m.wall}` : 'Assistant'}</div>
                </div>
              </div>
            ))}
            {busy && (
              <div className="flex justify-start" role="status" aria-label="The assistant is typing">
                <div className="rounded-2xl rounded-bl-md bg-white border border-slate-200 shadow-sm px-4 py-3 flex gap-1.5">
                  {[0, 150, 300].map((d) => <span key={d} className="h-2 w-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: `${d}ms` }} />)}
                </div>
              </div>
            )}
            <div ref={end} />
          </div>

          <div className="px-3 pt-2 flex flex-wrap gap-1.5 border-t border-slate-100 bg-white max-h-24 overflow-y-auto">
            {(lastBot?.reply?.suggestions ?? START_SUGGESTIONS).map((q) => (
              <button key={q} disabled={busy} onClick={() => send(q)} className="rounded-full border border-sky-300 bg-sky-50 text-sky-900 text-xs font-medium px-2.5 py-1 hover:bg-sky-100 disabled:opacity-50">{q}</button>
            ))}
          </div>
          <form className="p-3 flex gap-2 bg-white" onSubmit={(e) => { e.preventDefault(); void send(text) }}>
            <input ref={box} className="input !rounded-full !px-4" value={text} maxLength={300} onChange={(e) => setText(e.target.value)} placeholder="Ask about your order…" aria-label="Your question" />
            <button className="btn-primary !rounded-full !px-4" disabled={busy || !text.trim()} aria-label="Send"><Icon name="send" size={16} /></button>
          </form>
          <div className="text-[10px] text-slate-400 text-center pb-2 px-3">Read-only assistant. It cannot change orders, and does not share costs or other customers' data.</div>
        </section>
      )}
    </>
  )
}
