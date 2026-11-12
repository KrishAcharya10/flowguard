// Driver app (mobile first): big tap targets, one obvious next action. Every button calls the backend;
// the coordinator and customer see the result without refreshing.
import { useState } from 'react'
import { api, refreshAll, uploadFile, useApi, type DriverBooking, type DriverHistory, type DriverShipment } from '../api/client'
import { Chip, DownloadButton, FileDrop } from '../components/Documents'
import Icon from '../components/Icons'
import { Notice, State } from '../components/ui'
import { fmtTime } from '../lib/format'

const STATUS_TONE: Record<string, string> = {
  PLANNED: 'bg-slate-200 text-slate-800', LOADING: 'bg-sky-200 text-sky-900', AT_PLANT_GATE: 'bg-sky-200 text-sky-900',
  IN_TRANSIT: 'bg-emerald-200 text-emerald-900', ARRIVED_AT_CUSTOMER_GATE: 'bg-amber-200 text-amber-900', DELIVERED: 'bg-slate-200 text-slate-800',
}

function ReportSheet({ s, onDone }: { s: DriverShipment; onDone: (msg: string) => void }) {
  const [kind, setKind] = useState<'BREAKDOWN' | 'ROAD_HAZARD' | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const send = async () => {
    if (!kind) return
    setBusy(true)
    setErr('')
    try {
      const r = await api<{ message: string }>(`/api/transporter/shipments/${s.id}/report`, { method: 'POST', body: { kind, note: note.trim() || null } })
      setKind(null)
      setNote('')
      onDone(r.message)
      refreshAll()
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  if (!kind) {
    return (
      <div className="grid grid-cols-2 gap-2">
        <button className="btn-secondary !min-h-[52px] !text-sm flex-col" onClick={() => setKind('BREAKDOWN')}><Icon name="wrench" />Report breakdown</button>
        <button className="btn-secondary !min-h-[52px] !text-sm flex-col" onClick={() => setKind('ROAD_HAZARD')}><Icon name="alert" />Report road hazard</button>
      </div>
    )
  }
  return (
    <div className="rounded-xl border border-red-300 bg-red-50 p-3 space-y-2">
      <div className="font-bold text-red-900">{kind === 'BREAKDOWN' ? 'Report a breakdown' : 'Report a road hazard'}</div>
      <p className="text-xs text-red-900">{kind === 'BREAKDOWN' ? 'The control tower is told at once and your arrival time is recalculated.' : 'A hazard slows the road ahead. The control tower is told at once.'}</p>
      <label className="block text-sm font-medium">What happened? (optional)
        <textarea className="input mt-1" rows={2} maxLength={200} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. tyre burst, waiting for the service truck" />
      </label>
      {err && <Notice kind="error">{err}</Notice>}
      <div className="grid grid-cols-2 gap-2">
        <button className="btn-secondary !min-h-[48px]" onClick={() => setKind(null)} disabled={busy}>Cancel</button>
        <button className="btn-danger !min-h-[48px]" onClick={send} disabled={busy}>{busy ? 'Sending…' : 'Send report'}</button>
      </div>
    </div>
  )
}

const stamp = (iso: string) => new Date(iso).toLocaleString('en-GB', { timeZone: 'Asia/Kolkata', weekday: 'short', day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false }) + ' IST'
const BOOKING_TONE: Record<string, 'blue' | 'amber' | 'green' | 'slate' | 'red'> = { BOOKED: 'blue', CHECKED_IN: 'amber', COMPLETED: 'green', CANCELLED: 'slate', MISSED: 'red' }

function GateAppointment({ b }: { b: DriverBooking }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const checkIn = async () => {
    setBusy(true)
    setMsg(null)
    try { await api(`/api/transporter/gate/bookings/${b.id}/check-in`, { method: 'POST' }); setMsg({ kind: 'ok', text: 'Checked in at the plant gate.' }); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className="rounded-xl border border-sky-300 bg-gradient-to-br from-sky-50 to-white p-3 space-y-2" data-testid="gate-appointment">
      <div className="flex items-center gap-2"><span className="h-9 w-9 rounded-lg bg-sky-600 text-white flex items-center justify-center"><Icon name="gate" size={18} /></span>
        <div className="flex-1"><div className="text-xs font-semibold uppercase text-sky-900">Gate appointment</div><div className="font-bold text-navy-900">{stamp(b.slot_start)}</div></div>
        <Chip tone={BOOKING_TONE[b.status]}>{b.status.replace('_', ' ')}</Chip></div>
      <div className="text-sm">{b.gate_name}</div>
      <div className="text-xs text-slate-600">{b.gate_instructions}</div>
      <div className="text-xs text-slate-500">Vehicle {b.vehicle_label.replace(' (fictional)', '')} · {b.product_code} · {b.quantity_tonnes} t · simulated time</div>
      {b.status === 'BOOKED' && <button className="btn-primary w-full !min-h-[52px] !text-base !rounded-xl" disabled={busy || !b.can_check_in} onClick={checkIn}>Check in at the gate</button>}
      {b.status === 'BOOKED' && !b.can_check_in && b.check_in_hint && <p className="text-xs text-amber-800">{b.check_in_hint}</p>}
      {b.status === 'CHECKED_IN' && <Notice kind="ok">You are checked in{b.checked_in_at ? ` (${stamp(b.checked_in_at)})` : ''}. Wait to be called to the loading bay.</Notice>}
      {b.status === 'MISSED' && <Notice kind="error">This appointment was missed. The control tower will rebook you.</Notice>}
      {b.status === 'CANCELLED' && <Notice kind="warn">This appointment was cancelled{b.cancel_reason ? `: ${b.cancel_reason}` : ''}.</Notice>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
    </div>
  )
}

function PodUpload({ s, replace = false }: { s: DriverShipment; replace?: boolean }) {
  const [file, setFile] = useState<File | null>(null)
  const [recipient, setRecipient] = useState(s.pod_recipient ?? '')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const submit = async () => {
    if (!file) return
    setBusy(true)
    setMsg(null)
    try {
      const q = new URLSearchParams({ filename: file.name, recipient_name: recipient.trim() })
      const r = await uploadFile<{ message: string }>(`/api/transporter/shipments/${s.id}/pod-document?${q}`, file)
      setMsg({ kind: 'ok', text: r.message })
      setFile(null)
      refreshAll()
    } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  const noDoc = async () => {
    setBusy(true)
    setMsg(null)
    try { await api(`/api/transporter/shipments/${s.id}/pod`, { method: 'POST', body: { recipient_name: recipient } }); setMsg({ kind: 'ok', text: 'Proof of delivery recorded.' }); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-2.5">
      <div className="text-xs font-semibold uppercase text-slate-500">{replace ? 'Replace the proof of delivery document' : 'Proof of delivery'}</div>
      <label className="block text-sm font-medium">Received by (name)
        <input className="input mt-1 !py-3 !text-base" value={recipient} onChange={(e) => setRecipient(e.target.value)} minLength={2} maxLength={80} />
      </label>
      <FileDrop file={file} onFile={setFile} label="Photo or signed delivery note" />
      <button className="btn-primary w-full !min-h-[60px] !text-base !rounded-xl" disabled={busy || !file || recipient.trim().length < 2} onClick={submit}><Icon name="upload" size={18} />{replace ? 'Upload replacement' : 'Upload proof of delivery'}</button>
      {!replace && <button className="w-full text-sm underline text-slate-600" disabled={busy || recipient.trim().length < 2} onClick={noDoc}>No document? Record the delivery without one</button>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
    </div>
  )
}

function ShipmentCard({ s, booking }: { s: DriverShipment; booking?: DriverBooking }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [recipient, setRecipient] = useState('')
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true)
    setMsg(null)
    try { await fn(); setMsg({ kind: 'ok', text: ok }); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  const isPod = s.state === 'ARRIVED_AT_CUSTOMER_GATE'
  return (
    <section className="rounded-2xl bg-white border border-slate-200 shadow-sm overflow-hidden" data-testid={`driver-card-${s.id}`}>
      <div className="bg-navy-900 text-white p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-slate-300">{s.id} · {s.vehicle_label.replace(' (fictional)', '')}{s.lot_type !== 'SINGLE' ? ` · ${s.lot_type.toLowerCase()} lot` : ''}</span>
          <span className={`text-xs font-bold rounded-full px-2.5 py-1 ${STATUS_TONE[s.state]}`}>{s.state_label}</span>
        </div>
        <div className="text-xl font-bold mt-1 leading-tight">{s.destination_name}</div>
        <div className="text-sm text-slate-200">{s.customer_name.replace(' (fictional)', '')}{s.priority === 'HIGH' ? ' · PRIORITY' : ''}</div>
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <div><div className="text-[11px] uppercase text-slate-300">Load</div>{s.product_code} · {s.quantity_tonnes} t</div>
          <div><div className="text-[11px] uppercase text-slate-300">Deliver by</div>{fmtTime(s.promised_at)}</div>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {booking && <GateAppointment b={booking} />}
        <div>
          <div className="flex justify-between text-sm"><span className="font-semibold">Route progress · {s.route_name}{s.alternative_route_name ? ` via ${s.alternative_route_name}` : ''}</span><span className="font-bold">{s.progress_pct}%</span></div>
          <div className="relative h-3 rounded-full bg-slate-200 mt-1.5" role="progressbar" aria-valuenow={s.progress_pct} aria-valuemin={0} aria-valuemax={100} aria-label="Route progress">
            <div className="h-3 rounded-full bg-navy-700" style={{ width: `${s.progress_pct}%` }} />
          </div>
          <div className="text-xs text-slate-500 mt-1">{Math.round(s.progress_km)} of {Math.round(s.total_km)} km{s.last_reported_at ? ` · last position ${fmtTime(s.last_reported_at)}` : ' · not departed yet'}</div>
        </div>

        {s.instruction && <Notice kind="warn"><strong>From the control tower:</strong> {s.instruction}</Notice>}
        {s.active_report && <Notice kind="error"><strong>{s.active_report}.</strong> The control tower knows. Keep them updated.</Notice>}

        <ol className="space-y-1.5" aria-label="Milestones">
          {s.milestones.map((m, i) => (
            <li key={m.state} className={`flex items-center gap-3 rounded-lg px-2 py-1.5 ${m.current ? 'bg-navy-50 border border-navy-700' : ''}`}>
              <span className={`h-7 w-7 shrink-0 rounded-full flex items-center justify-center text-xs font-bold ${m.current ? 'bg-navy-800 text-white' : m.done ? 'bg-emerald-600 text-white' : 'bg-slate-200 text-slate-500'}`}>{m.done && !m.current ? '✓' : i + 1}</span>
              <span className={`flex-1 text-sm ${m.current ? 'font-bold text-navy-900' : m.done ? 'text-slate-700' : 'text-slate-400'}`}>{m.label}</span>
              <span className="text-[11px] text-slate-500">{m.occurred_at ? fmtTime(m.occurred_at) : ''}</span>
            </li>
          ))}
        </ol>

        {s.next_state && !isPod && (
          <div>
            <div className="text-xs font-semibold uppercase text-slate-500 mb-1">Next milestone</div>
            <button className="btn-primary w-full !min-h-[60px] !text-base !rounded-xl" disabled={busy}
              onClick={() => run(() => api(`/api/transporter/shipments/${s.id}/milestones`, { method: 'POST', body: { to_state: s.next_state } }), 'Milestone recorded.')}>
              Confirm: {s.next_state_label}
            </button>
          </div>
        )}
        {isPod && <PodUpload s={s} />}
        {s.state === 'DELIVERED' && (
          <div className="space-y-3">
            <Notice kind="ok">Delivered. Received by {s.pod_recipient}. Thank you.</Notice>
            {s.pod_document_id ? (
              <div className="rounded-xl border border-emerald-300 bg-emerald-50 p-3 flex flex-wrap items-center gap-2 text-sm"><Icon name="file" className="text-emerald-800" /><div className="flex-1 min-w-0"><div className="font-semibold truncate">{s.pod_document_name}</div><div className="text-xs text-slate-600">Proof of delivery uploaded{s.pod_uploaded_at ? ` ${stamp(s.pod_uploaded_at)}` : ''}</div></div><DownloadButton id={s.pod_document_id} name={s.pod_document_name ?? 'proof-of-delivery'} /></div>
            ) : <Notice kind="warn">No document was uploaded for this delivery. You can add one below.</Notice>}
            <details><summary className="text-sm underline text-slate-600 cursor-pointer">{s.pod_document_id ? 'Replace the document' : 'Upload the document'}</summary><div className="mt-2"><PodUpload s={s} replace /></div></details>
          </div>
        )}

        {s.can_report && <div><div className="text-xs font-semibold uppercase text-slate-500 mb-1">Problem on the road?</div><ReportSheet s={s} onDone={(t) => setMsg({ kind: 'ok', text: t })} /></div>}
        {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
      </div>
    </section>
  )
}

function History() {
  const { data, error, loading, reload } = useApi<DriverHistory[]>('/api/transporter/me/history')
  const onTime = (data ?? []).filter((h) => h.on_time).length
  return (
    <div className="space-y-3">
      {data && data.length > 0 && <div className="rounded-xl bg-white border border-slate-200 p-3 text-sm"><strong>{data.length}</strong> recent deliveries · <strong>{onTime}</strong> on time ({Math.round((100 * onTime) / data.length)}%)</div>}
      <State loading={loading && !data} error={error} empty={!!data && data.length === 0} emptyText="No completed deliveries yet." onRetry={reload} />
      <ul className="space-y-2">
        {data?.map((h) => (
          <li key={h.shipment_id} className="rounded-xl bg-white border border-slate-200 p-3 flex items-center gap-3">
            <span className={`h-9 w-9 rounded-full flex items-center justify-center ${h.on_time ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'}`}><Icon name={h.on_time ? 'check' : 'clock'} /></span>
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-sm truncate">{h.destination_name}</div>
              <div className="text-xs text-slate-500">{h.shipment_id} · {h.product_code} · {h.quantity_tonnes} t</div>
              <div className="text-xs text-slate-500">Arrived {fmtTime(h.arrived_at)} · promised {fmtTime(h.promised_at)}</div>
            </div>
            <span className={`text-[11px] font-bold rounded px-1.5 py-0.5 ${h.on_time ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'}`}>{h.on_time ? 'On time' : 'Late'}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function TransporterPortal() {
  const { data, error, loading, reload } = useApi<DriverShipment[]>('/api/transporter/me/shipments')
  const gate = useApi<DriverBooking[]>('/api/transporter/me/gate')
  const [tab, setTab] = useState<'today' | 'history'>('today')
  const bookingFor = (id: string) => (gate.data ?? []).find((b) => b.shipment_id === id && (b.status === 'BOOKED' || b.status === 'CHECKED_IN')) ?? (gate.data ?? []).find((b) => b.shipment_id === id)
  const current = (data ?? []).filter((s) => s.state !== 'DELIVERED')
  const done = (data ?? []).filter((s) => s.state === 'DELIVERED')
  return (
    <div className="max-w-md mx-auto pb-24">
      <div className="mb-3 flex items-end justify-between">
        <h1 className="text-xl font-bold text-navy-900">{tab === 'today' ? 'My deliveries' : 'Delivery history'}</h1>
        {tab === 'today' && <span className="text-xs text-slate-500">{current.length} active</span>}
      </div>
      {tab === 'today' ? (
        <div className="space-y-4">
          <State loading={loading && !data} error={error} empty={!!data && current.length === 0 && done.length === 0} emptyText="No shipment is assigned to you right now. New assignments appear here by themselves." onRetry={reload} />
          {data && current.length === 0 && done.length > 0 && <Notice kind="ok">All your deliveries are complete. New assignments appear here by themselves.</Notice>}
          {current.map((s) => <ShipmentCard key={s.id} s={s} booking={bookingFor(s.id)} />)}
          {done.map((s) => <ShipmentCard key={s.id} s={s} booking={bookingFor(s.id)} />)}
        </div>
      ) : <History />}
      <nav className="fixed bottom-0 inset-x-0 z-30 bg-white border-t border-slate-200 grid grid-cols-2" aria-label="Driver navigation">
        {([['today', 'My deliveries', 'truck'], ['history', 'History', 'history']] as const).map(([k, label, icon]) => (
          <button key={k} onClick={() => setTab(k)} aria-current={tab === k ? 'page' : undefined}
            className={`py-3 flex flex-col items-center gap-0.5 text-xs font-semibold ${tab === k ? 'text-navy-900 border-t-2 border-navy-800 -mt-px' : 'text-slate-500'}`}>
            <Icon name={icon} />{label}
          </button>
        ))}
      </nav>
    </div>
  )
}
