// Create an order and assign it to a transporter, a free driver and a vehicle. Persisted by the backend.
import { useState, type FormEvent } from 'react'
import { api, refreshAll, type OrderCreated, type ReferenceData } from '../api/client'
import { fmtTime } from '../lib/format'
import { Notice } from './ui'

export default function NewOrderDialog({ refData, onClose, onOpenShipment }: { refData: ReferenceData; onClose: () => void; onOpenShipment: (id: string) => void }) {
  const firstRoute = refData.order_routes[0]?.route_id ?? ''
  const [f, setF] = useState({ route_id: firstRoute, transporter_id: refData.transporters.find((t) => (refData.free_drivers[t.id] ?? 0) > 0)?.id ?? refData.transporters[0]?.id ?? '', product_code: refData.products[0] ?? '', quantity_tonnes: '20', priority: 'NORMAL', loading_in_h: '1', promise: 'auto', promised_in_h: '12' })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [done, setDone] = useState<OrderCreated | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const r = await api<OrderCreated>('/api/orders', {
        method: 'POST',
        body: {
          route_id: f.route_id, transporter_id: f.transporter_id, product_code: f.product_code, quantity_tonnes: Number(f.quantity_tonnes),
          priority: f.priority, loading_in_h: Number(f.loading_in_h), promised_in_h: f.promise === 'auto' ? null : Number(f.promised_in_h),
        },
      })
      setDone(r)
      refreshAll()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }
  const route = refData.order_routes.find((r) => r.route_id === f.route_id)
  const input = 'input mt-1'
  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-4 bg-black/40" role="dialog" aria-modal="true" aria-label="Create order">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-xl max-h-[90vh] overflow-y-auto">
        <div className="px-5 py-3 border-b border-slate-200 flex items-center justify-between">
          <h2 className="text-lg font-bold text-navy-900">New order</h2>
          <button className="btn-secondary" onClick={onClose}>Close</button>
        </div>
        {done ? (
          <div className="p-5 space-y-3">
            <Notice kind="ok"><strong>{done.message}</strong></Notice>
            <dl className="grid grid-cols-2 gap-y-1 text-sm">
              <dt className="text-slate-500">Order / shipment</dt><dd>{done.order_id} / {done.shipment_id}</dd>
              <dt className="text-slate-500">Customer</dt><dd>{done.customer_name}</dd>
              <dt className="text-slate-500">Transporter</dt><dd>{done.transporter_name}</dd>
              <dt className="text-slate-500">Driver</dt><dd>{done.driver_name} · login <strong>{done.driver_username}</strong></dd>
              <dt className="text-slate-500">Vehicle</dt><dd>{done.vehicle_label}</dd>
              <dt className="text-slate-500">Planned loading</dt><dd>{fmtTime(done.planned_loading_at)}</dd>
              <dt className="text-slate-500">Promised delivery</dt><dd>{fmtTime(done.promised_at)}</dd>
            </dl>
            <p className="text-sm text-slate-600">The driver can now log in as <strong>{done.driver_username}</strong> and see this shipment; the customer sees the order in their portal.</p>
            <div className="flex gap-2"><button className="btn-primary" onClick={() => onOpenShipment(done.shipment_id)}>Open shipment</button><button className="btn-secondary" onClick={() => { setDone(null) }}>Create another</button></div>
          </div>
        ) : (
          <form onSubmit={submit} className="p-5 grid sm:grid-cols-2 gap-3">
            <label className="sm:col-span-2 text-sm font-medium">Destination (route)
              <select className={input} value={f.route_id} onChange={(e) => setF({ ...f, route_id: e.target.value })}>
                {refData.order_routes.map((r) => <option key={r.route_id} value={r.route_id}>{r.route_name} → {r.customer_name}</option>)}
              </select>
              {route && <span className="text-xs text-slate-500">Delivers to {route.destination_name}</span>}
            </label>
            <label className="sm:col-span-2 text-sm font-medium">Transporter
              <select className={input} value={f.transporter_id} onChange={(e) => setF({ ...f, transporter_id: e.target.value })}>
                {refData.transporters.map((t) => <option key={t.id} value={t.id} disabled={(refData.free_drivers[t.id] ?? 0) === 0}>{t.name} · {refData.free_drivers[t.id] ?? 0} free driver(s)</option>)}
              </select>
            </label>
            <label className="text-sm font-medium">Product
              <select className={input} value={f.product_code} onChange={(e) => setF({ ...f, product_code: e.target.value })}>{refData.products.map((p) => <option key={p}>{p}</option>)}</select>
            </label>
            <label className="text-sm font-medium">Quantity (tonnes)
              <input className={input} type="number" min="1" max="40" step="0.5" value={f.quantity_tonnes} onChange={(e) => setF({ ...f, quantity_tonnes: e.target.value })} required />
            </label>
            <label className="text-sm font-medium">Priority
              <select className={input} value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })}><option value="NORMAL">Normal</option><option value="HIGH">High</option></select>
            </label>
            <label className="text-sm font-medium">Loading starts in (hours)
              <input className={input} type="number" min="0" max="24" step="0.5" value={f.loading_in_h} onChange={(e) => setF({ ...f, loading_in_h: e.target.value })} required />
            </label>
            <fieldset className="sm:col-span-2 text-sm">
              <legend className="font-medium">Promised delivery</legend>
              <label className="mr-4"><input type="radio" name="promise" checked={f.promise === 'auto'} onChange={() => setF({ ...f, promise: 'auto' })} /> Automatic (expected arrival + 2 h buffer)</label>
              <label><input type="radio" name="promise" checked={f.promise === 'custom'} onChange={() => setF({ ...f, promise: 'custom' })} /> In </label>
              <input className="input !w-20 inline-block mx-1" type="number" min="1" max="240" disabled={f.promise !== 'custom'} value={f.promised_in_h} onChange={(e) => setF({ ...f, promised_in_h: e.target.value })} aria-label="Promised in hours" /> hours
            </fieldset>
            {error && <div className="sm:col-span-2"><Notice kind="error">{error}</Notice></div>}
            <div className="sm:col-span-2 flex justify-end gap-2">
              <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
              <button className="btn-primary" disabled={busy}>{busy ? 'Creating…' : 'Create and assign'}</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
