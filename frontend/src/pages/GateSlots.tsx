// Gate slot booking (coordinator): hourly appointment schedule for the Plant X gate.
// All times are SIMULATED (shown in IST); slots are judged against the simulation clock, never the real clock.
import { useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { api, refreshAll, useApi, type Booking, type GateOverview, type ReferenceData, type Shipment, type Slot } from '../api/client'
import { Chip } from '../components/Documents'
import Icon from '../components/Icons'
import { Card, Notice, PageHeader, State } from '../components/ui'

const dayKey = (iso: string) => new Date(iso).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
const hhmm = (iso: string) => new Date(iso).toLocaleTimeString('en-GB', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false })
const dayLabel = (iso: string) => new Date(iso).toLocaleDateString('en-GB', { timeZone: 'Asia/Kolkata', weekday: 'short', day: '2-digit', month: 'short' })
const stamp = (iso: string) => `${dayLabel(iso)}, ${hhmm(iso)} IST`

const STATE_TONE: Record<Slot['state'], { chip: 'green' | 'amber' | 'red' | 'slate' | 'blue'; bar: string; label: string }> = {
  OPEN: { chip: 'green', bar: 'bg-emerald-500', label: 'Open' }, FULL: { chip: 'amber', bar: 'bg-amber-500', label: 'Full' },
  OVERBOOKED: { chip: 'red', bar: 'bg-red-600', label: 'Overbooked' }, UNAVAILABLE: { chip: 'slate', bar: 'bg-slate-400', label: 'Unavailable' },
  PAST: { chip: 'slate', bar: 'bg-slate-300', label: 'Past' },
}
const BOOKING_TONE: Record<string, 'blue' | 'amber' | 'green' | 'slate' | 'red'> = { BOOKED: 'blue', CHECKED_IN: 'amber', COMPLETED: 'green', CANCELLED: 'slate', MISSED: 'red' }
const PRE = ['PLANNED', 'LOADING', 'AT_PLANT_GATE']

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-black/40" role="dialog" aria-modal="true" aria-label={title}>
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between"><h2 className="text-lg font-bold text-navy-900">{title}</h2><button className="btn-secondary" onClick={onClose}>Close</button></div>
        <div className="p-5 space-y-3">{children}</div>
      </div>
    </div>
  )
}

function useAction() {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const run = async (fn: () => Promise<unknown>, done: () => void) => {
    setBusy(true)
    setErr('')
    try { await fn(); refreshAll(); done() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return { busy, err, run }
}

function BookDialog({ slot, candidates, refData, onClose }: { slot: Slot; candidates: Shipment[]; refData: ReferenceData; onClose: () => void }) {
  const [sid, setSid] = useState(candidates[0]?.id ?? '')
  const ship = candidates.find((c) => c.id === sid)
  const drivers = refData.drivers.filter((d) => d.transporter_id === ship?.transporter_id)
  const defaultDriver = drivers.find((d) => d.name === ship?.driver_name)?.id
  const [driver, setDriver] = useState<number | ''>('')
  const { busy, err, run } = useAction()
  return (
    <Modal title={`Book a gate slot · ${stamp(slot.slot_start)}`} onClose={onClose}>
      <p className="text-sm text-slate-600">{slot.booked} of {slot.capacity} places taken. Simulated time, Indian Standard Time.</p>
      {candidates.length === 0 ? <Notice kind="info">Every shipment that has not left Plant X already has an active booking.</Notice> : (
        <>
          <label className="block text-sm font-medium">Shipment
            <select aria-label="Shipment" className="input mt-1" value={sid} onChange={(e) => { setSid(e.target.value); setDriver('') }}>
              {candidates.map((c) => <option key={c.id} value={c.id}>{c.id} · {c.customer_name.replace(' (fictional)', '')} · {c.state_label}</option>)}
            </select>
          </label>
          {ship && (
            <div className="grid sm:grid-cols-2 gap-3">
              <label className="block text-sm font-medium">Transporter
                <select aria-label="Transporter" className="input mt-1" value={ship.transporter_id} disabled><option value={ship.transporter_id}>{ship.transporter_name.replace(' (fictional)', '')}</option></select>
                <span className="text-xs text-slate-500">from the shipment</span>
              </label>
              <label className="block text-sm font-medium">Driver
                <select aria-label="Driver" className="input mt-1" value={driver === '' ? defaultDriver ?? '' : driver} onChange={(e) => setDriver(Number(e.target.value))}>
                  {drivers.map((d) => <option key={d.id} value={d.id}>{d.name.replace(' (fictional)', '')}{d.id === defaultDriver ? ' (assigned)' : ''}</option>)}
                </select>
              </label>
              <div className="sm:col-span-2 text-sm rounded-lg bg-slate-50 border border-slate-200 p-2">Vehicle: <strong>{ship.vehicle_label.replace(' (fictional)', '')}</strong> · {ship.product_code} · {ship.quantity_tonnes} t</div>
            </div>
          )}
        </>
      )}
      {err && <Notice kind="error">{err}</Notice>}
      <div className="flex justify-end gap-2">
        <button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || !ship} onClick={() => run(() => api('/api/gate/bookings', { method: 'POST', body: { shipment_id: sid, slot_id: slot.id, transporter_id: ship!.transporter_id, driver_user_id: driver === '' ? defaultDriver ?? null : driver } }), onClose)}>{busy ? 'Booking…' : 'Book slot'}</button>
      </div>
    </Modal>
  )
}

function RescheduleDialog({ b, slots, onClose }: { b: Booking; slots: Slot[]; onClose: () => void }) {
  const options = slots.filter((s) => s.state === 'OPEN' && s.id !== b.slot_id)
  const [to, setTo] = useState(options[0]?.id ?? 0)
  const { busy, err, run } = useAction()
  return (
    <Modal title={`Reschedule ${b.shipment_id}`} onClose={onClose}>
      <p className="text-sm text-slate-600">Current slot: <strong>{stamp(b.slot_start)}</strong>. The old place is released and the new one reserved in one step.</p>
      <label className="block text-sm font-medium">New slot
        <select aria-label="New slot" className="input mt-1" value={to} onChange={(e) => setTo(Number(e.target.value))}>
          {options.map((s) => <option key={s.id} value={s.id}>{stamp(s.slot_start)} · {s.available} free</option>)}
        </select>
      </label>
      {err && <Notice kind="error">{err}</Notice>}
      <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy || !to} onClick={() => run(() => api(`/api/gate/bookings/${b.id}/reschedule`, { method: 'POST', body: { slot_id: to } }), onClose)}>Reschedule</button></div>
    </Modal>
  )
}

function CancelDialog({ b, onClose }: { b: Booking; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const { busy, err, run } = useAction()
  return (
    <Modal title={`Cancel the booking for ${b.shipment_id}?`} onClose={onClose}>
      <p className="text-sm text-slate-600">{stamp(b.slot_start)}. The place in the slot is released.</p>
      <label className="block text-sm font-medium">Reason (optional)<input className="input mt-1" maxLength={200} value={reason} onChange={(e) => setReason(e.target.value)} /></label>
      {err && <Notice kind="error">{err}</Notice>}
      <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Keep booking</button>
        <button className="btn-danger" disabled={busy} onClick={() => run(() => api(`/api/gate/bookings/${b.id}/cancel`, { method: 'POST', body: { reason: reason || null } }), onClose)}>Cancel booking</button></div>
    </Modal>
  )
}

function SlotDialog({ slot, onClose }: { slot: Slot; onClose: () => void }) {
  const [cap, setCap] = useState(String(slot.capacity))
  const [closed, setClosed] = useState(slot.state === 'UNAVAILABLE')
  const [note, setNote] = useState(slot.note)
  const { busy, err, run } = useAction()
  return (
    <Modal title={`Slot settings · ${stamp(slot.slot_start)}`} onClose={onClose}>
      <label className="block text-sm font-medium">Capacity (vehicles)<input className="input mt-1" type="number" min={0} max={50} value={cap} onChange={(e) => setCap(e.target.value)} /></label>
      {Number(cap) < slot.booked && <Notice kind="warn">{slot.booked} vehicles are already booked: lowering the capacity to {cap} will mark this slot as <strong>overbooked</strong>. Existing bookings are kept.</Notice>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={closed} onChange={(e) => setClosed(e.target.checked)} />Mark this slot unavailable (for example maintenance)</label>
      <label className="block text-sm font-medium">Note<input className="input mt-1" maxLength={120} value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. weighbridge calibration" /></label>
      {err && <Notice kind="error">{err}</Notice>}
      <div className="flex justify-end gap-2"><button className="btn-secondary" onClick={onClose}>Cancel</button>
        <button className="btn-primary" disabled={busy} onClick={() => run(() => api(`/api/gate/slots/${slot.id}`, { method: 'PUT', body: { capacity: Number(cap), closed, note } }), onClose)}>Save</button></div>
    </Modal>
  )
}

function BookingRow({ b, onReschedule, onCancel }: { b: Booking; onReschedule?: () => void; onCancel?: () => void }) {
  const [err, setErr] = useState('')
  const complete = async () => { setErr(''); try { await api(`/api/gate/bookings/${b.id}/complete`, { method: 'POST' }); refreshAll() } catch (e) { setErr((e as Error).message) } }
  return (
    <li className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs" data-testid={`booking-${b.id}`}>
      <Link className="font-bold text-navy-700 underline" to={`/shipments/${b.shipment_id}`}>{b.shipment_id}</Link>
      <span className="text-slate-600">{b.vehicle_label.replace(' (fictional)', '')} · {b.driver_name?.replace(' (fictional)', '') ?? 'no driver'}</span>
      <Chip tone={BOOKING_TONE[b.status]}>{b.status.replace('_', ' ')}</Chip>
      {b.rescheduled_from && <span className="text-slate-400">moved from {hhmm(b.rescheduled_from)}</span>}
      <span className="ml-auto flex gap-1">
        {b.status === 'BOOKED' && onReschedule && <button className="btn-secondary !py-0.5 !px-2 !text-[11px]" onClick={onReschedule}>Reschedule</button>}
        {b.status === 'BOOKED' && onCancel && <button className="btn-secondary !py-0.5 !px-2 !text-[11px]" onClick={onCancel}>Cancel</button>}
        {b.status === 'CHECKED_IN' && <button className="btn-secondary !py-0.5 !px-2 !text-[11px]" onClick={complete}>Mark completed</button>}
      </span>
      {err && <span className="basis-full text-red-700">{err}</span>}
    </li>
  )
}

export default function GateSlots() {
  const ov = useApi<GateOverview>('/api/gate/overview')
  const upcoming = useApi<Booking[]>('/api/gate/bookings?scope=upcoming')
  const history = useApi<Booking[]>('/api/gate/bookings?scope=history')
  const ships = useApi<Shipment[]>('/api/shipments')
  const ref = useApi<ReferenceData>('/api/reference-data')
  const [day, setDay] = useState<string | null>(null)
  const [hidePast, setHidePast] = useState(true)
  const [dlg, setDlg] = useState<{ kind: 'book' | 'slot'; slot: Slot } | { kind: 'move' | 'cancel'; b: Booking } | null>(null)

  const today = ov.data ? dayKey(ov.data.sim_now) : null
  const days = useMemo(() => [...new Set((ov.data?.slots ?? []).map((s) => dayKey(s.slot_start)))], [ov.data])
  const active = day ?? today
  const slots = useMemo(() => (ov.data?.slots ?? []).filter((s) => dayKey(s.slot_start) === active && (!hidePast || s.state !== 'PAST')), [ov.data, active, hidePast])
  const daySlots = (ov.data?.slots ?? []).filter((s) => dayKey(s.slot_start) === active)
  const usable = daySlots.filter((s) => s.state !== 'UNAVAILABLE')
  const cap = usable.reduce((n, s) => n + s.capacity, 0)
  const booked = daySlots.reduce((n, s) => n + s.booked, 0)
  const full = daySlots.filter((s) => s.state === 'FULL' || s.state === 'OVERBOOKED').length
  const over = daySlots.filter((s) => s.state === 'OVERBOOKED').length
  const unavailable = daySlots.filter((s) => s.state === 'UNAVAILABLE').length
  const bookedIds = new Set((upcoming.data ?? []).map((b) => b.shipment_id))
  const candidates = (ships.data ?? []).filter((s) => s.disposition === 'ACTIVE' && PRE.includes(s.state) && !bookedIds.has(s.id))

  if (!ov.data) return <State loading={ov.loading} error={ov.error} onRetry={ov.reload} />
  const openSlots = ov.data.slots.filter((s) => s.state === 'OPEN')
  const stat = (label: string, value: ReactNode, sub?: string, tone = 'text-navy-900') => (
    <div className="card p-3.5"><div className="label !text-[11px]">{label}</div><div className={`text-2xl font-bold ${tone}`}>{value}</div>{sub && <div className="text-[11px] text-slate-500">{sub}</div>}</div>
  )

  return (
    <div className="space-y-4">
      <PageHeader icon={<Icon name="gate" size={22} />} title="Gate slot booking" right={<div className="text-right text-sm"><div className="label !text-[10.5px]">Simulated time</div><div className="text-lg font-bold text-navy-900">{stamp(ov.data.sim_now)}</div><div className="text-[11px] text-slate-500">Check-in opens {ov.data.check_in_early_minutes} min before a slot · default capacity {ov.data.default_capacity}</div></div>}>{ov.data.gate_name}. Hourly appointments for trucks entering Plant X.</PageHeader>

      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="Day">
        {days.map((d) => {
          const first = ov.data!.slots.find((s) => dayKey(s.slot_start) === d)!
          return <button key={d} role="tab" aria-selected={active === d} onClick={() => setDay(d)} className={`px-3.5 py-2 rounded-xl text-sm font-semibold border ${active === d ? 'bg-navy-800 text-white border-navy-800 shadow' : 'bg-white text-navy-900 border-slate-300 hover:bg-slate-50'}`}>{dayLabel(first.slot_start)}{d === today ? ' · today' : ''}</button>
        })}
        <label className="ml-auto text-sm flex items-center gap-2"><input type="checkbox" checked={hidePast} onChange={(e) => setHidePast(e.target.checked)} />Hide past slots</label>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {stat('Capacity', cap, 'places in open slots')}
        {stat('Booked', booked, cap ? `${Math.round((100 * booked) / cap)}% utilised` : '')}
        {stat('Free places', Math.max(0, cap - booked), 'still bookable', 'text-emerald-700')}
        {stat('Full or overbooked', full, over ? `${over} overbooked` : 'no overbooking', full ? 'text-amber-700' : 'text-navy-900')}
        {stat('Unavailable', unavailable, 'closed slots', 'text-slate-600')}
      </div>

      <Card title={`Schedule · ${slots[0] ? dayLabel(slots[0].slot_start) : ''}`}>
        <div className="overflow-x-auto">
          <table className="w-full" data-testid="gate-schedule">
            <thead><tr className="border-b border-slate-200"><th className="w-24">Time (IST)</th><th className="w-52">Capacity</th><th className="w-32">Status</th><th>Bookings</th><th className="w-36"></th></tr></thead>
            <tbody>
              {slots.map((s) => {
                const tone = STATE_TONE[s.state]
                const pct = s.capacity ? Math.min(100, (100 * s.booked) / s.capacity) : s.booked ? 100 : 0
                return (
                  <tr key={s.id} className={`border-b border-slate-100 ${s.state === 'PAST' ? 'opacity-60' : ''} ${s.state === 'UNAVAILABLE' ? 'bg-slate-50' : s.state === 'OVERBOOKED' ? 'bg-red-50' : ''}`} data-testid={`slot-${hhmm(s.slot_start).slice(0, 2)}`}>
                    <td className="font-semibold tabular-nums">{hhmm(s.slot_start)}–{hhmm(s.slot_end)}</td>
                    <td>
                      <div className="flex items-center gap-2"><div className="h-2.5 flex-1 rounded-full bg-slate-200 overflow-hidden"><div className={`h-2.5 ${tone.bar}`} style={{ width: `${pct}%` }} /></div><span className="text-xs font-bold tabular-nums w-10 text-right">{s.booked}/{s.capacity}</span></div>
                      <div className="text-[11px] text-slate-500">{s.state === 'UNAVAILABLE' ? s.note || 'closed' : `${s.available} free`}</div>
                    </td>
                    <td><Chip tone={tone.chip}>{tone.label}</Chip></td>
                    <td>{s.bookings.length === 0 ? <span className="text-xs text-slate-400">no bookings</span> : <ul className="space-y-1">{s.bookings.map((b) => <BookingRow key={b.id} b={b} onReschedule={() => setDlg({ kind: 'move', b })} onCancel={() => setDlg({ kind: 'cancel', b })} />)}</ul>}</td>
                    <td className="text-right whitespace-nowrap">
                      {s.state !== 'PAST' && <button className="btn-primary !py-1 !px-2.5 !text-xs" disabled={s.state !== 'OPEN'} onClick={() => setDlg({ kind: 'book', slot: s })}>Book</button>}{' '}
                      {s.state !== 'PAST' && <button className="btn-secondary !py-1 !px-2 !text-xs" aria-label={`Settings for ${hhmm(s.slot_start)}`} onClick={() => setDlg({ kind: 'slot', slot: s })}>Edit</button>}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
          {slots.length === 0 && <State empty emptyText="No slots to show for this day." />}
        </div>
      </Card>

      <div className="grid xl:grid-cols-2 gap-4">
        <Card title={`Upcoming bookings (${upcoming.data?.length ?? 0})`}>
          <State loading={upcoming.loading && !upcoming.data} error={upcoming.error} empty={!!upcoming.data && upcoming.data.length === 0} emptyText="No upcoming bookings." onRetry={upcoming.reload} />
          <ul className="space-y-2">{upcoming.data?.map((b) => (
            <li key={b.id} className="rounded-xl border border-slate-200 p-2.5 flex flex-wrap items-center gap-2">
              <span className="font-bold text-sm tabular-nums w-40">{stamp(b.slot_start)}</span>
              <Link className="font-semibold text-navy-700 underline text-sm" to={`/shipments/${b.shipment_id}`}>{b.shipment_id}</Link>
              <span className="text-xs text-slate-600">{b.vehicle_label.replace(' (fictional)', '')} · {b.driver_name?.replace(' (fictional)', '')} · {b.transporter_name.replace(' (fictional)', '')}</span>
              <Chip tone={BOOKING_TONE[b.status]}>{b.status.replace('_', ' ')}</Chip>
              {b.status === 'BOOKED' && <span className="ml-auto flex gap-1"><button className="btn-secondary !py-0.5 !px-2 !text-xs" onClick={() => setDlg({ kind: 'move', b })}>Reschedule</button><button className="btn-secondary !py-0.5 !px-2 !text-xs" onClick={() => setDlg({ kind: 'cancel', b })}>Cancel</button></span>}
            </li>))}</ul>
        </Card>
        <Card title={`Completed, cancelled and missed (${history.data?.length ?? 0})`}>
          <State loading={history.loading && !history.data} error={history.error} empty={!!history.data && history.data.length === 0} emptyText="Nothing yet." onRetry={history.reload} />
          <ul className="space-y-1.5 max-h-96 overflow-y-auto">{[...(history.data ?? [])].slice(0, 40).map((b) => (
            <li key={b.id} className="rounded-lg border border-slate-200 px-2.5 py-1.5 flex flex-wrap items-center gap-2 text-xs">
              <span className="font-semibold tabular-nums w-36">{stamp(b.slot_start)}</span><span className="font-semibold">{b.shipment_id}</span>
              <span className="text-slate-600">{b.vehicle_label.replace(' (fictional)', '')}</span><Chip tone={BOOKING_TONE[b.status]}>{b.status}</Chip>
              {b.cancel_reason && <span className="text-slate-500">“{b.cancel_reason}”</span>}
            </li>))}</ul>
        </Card>
      </div>

      {dlg?.kind === 'book' && ref.data && <BookDialog slot={dlg.slot} candidates={candidates} refData={ref.data} onClose={() => setDlg(null)} />}
      {dlg?.kind === 'slot' && <SlotDialog slot={dlg.slot} onClose={() => setDlg(null)} />}
      {dlg?.kind === 'move' && <RescheduleDialog b={dlg.b} slots={openSlots} onClose={() => setDlg(null)} />}
      {dlg?.kind === 'cancel' && <CancelDialog b={dlg.b} onClose={() => setDlg(null)} />}
    </div>
  )
}
