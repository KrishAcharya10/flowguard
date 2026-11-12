// Customer portal: delivery tracking. Uses only the customer allow-list endpoints: no costs, penalties,
// stock assumptions, transporter details or other customers' data.
import { useEffect, useState } from 'react'
import { api, refreshAll, useApi, type CustomerAlert, type CustomerDocument, type CustomerHistory, type CustomerOrder, type CustomerShipment } from '../api/client'
import ChatWidget from '../components/ChatWidget'
import { Chip, CustomerOrderDocs } from '../components/Documents'
import Icon from '../components/Icons'
import MapView from '../components/MapView'
import { Card, ConfidenceBadge, MilestoneBar, PageHeader, RiskBadge, State } from '../components/ui'
import { fmtEta, fmtTime, hoursBetween } from '../lib/format'

function Summary({ icon, label, value, tone }: { icon: string; label: string; value: number; tone: string }) {
  return (
    <div className="card p-3.5 flex items-center gap-3">
      <span className={`h-10 w-10 rounded-xl flex items-center justify-center ${tone}`}><Icon name={icon} size={20} /></span>
      <div><div className="text-2xl font-bold text-navy-900 leading-tight">{value}</div><div className="text-xs text-slate-600">{label}</div></div>
    </div>
  )
}

function ProgressBar({ pct, state }: { pct: number; state: string }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="font-semibold">Delivery progress</span><span className="font-bold">{pct}%</span></div>
      <div className="h-3 rounded-full bg-slate-200 mt-1.5" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label="Delivery progress">
        <div className={`h-3 rounded-full ${state === 'DELIVERED' ? 'bg-emerald-600' : 'bg-navy-700'}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function ShipmentView({ s, multi }: { s: CustomerShipment; multi: boolean }) {
  const done = s.state === 'ARRIVED_AT_CUSTOMER_GATE' || s.state === 'DELIVERED'
  return (
    <div className="border-t border-slate-200 pt-4 mt-4 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <strong className="text-sm">{s.id}{multi || s.lot_type !== 'SINGLE' ? ` · ${s.lot_type === 'SINGLE' ? 'delivery' : s.lot_type.toLowerCase() + ' delivery'}, ${s.quantity_tonnes} t` : ''}</strong>
        <span className="text-xs rounded-full bg-slate-100 text-slate-800 px-2 py-0.5 font-semibold">{s.state_label}</span>
        {s.risk_level && <RiskBadge level={s.risk_level} prefix="Delay risk" />}
        <ConfidenceBadge value={s.data_confidence} />
      </div>
      {!done && s.eta_from && s.eta_to && <p className="text-sm">Likely arrival between <strong>{fmtEta(s.eta_from)}</strong> and <strong>{fmtEta(s.eta_to)}</strong></p>}
      {s.delay_explanation && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-950" role="status">
          <div className="font-semibold mb-0.5">Why your delivery may be late</div>{s.delay_explanation}
        </div>
      )}
      {s.action_note && <p className="text-sm rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-900 p-3">{s.action_note} No action is required from you.</p>}
      <ProgressBar pct={s.progress_pct} state={s.state} />
      <MilestoneBar items={s.milestones} />
      <div className="grid lg:grid-cols-2 gap-4">
        <div>
          <div className="label mb-1.5">What has happened</div>
          {s.timeline.length === 0 && <p className="text-sm text-slate-500">Nothing yet.</p>}
          <ul className="space-y-2">
            {[...s.timeline].reverse().map((e, i) => (
              <li key={i} className="flex gap-2 text-sm"><span className="mt-1.5 h-2 w-2 rounded-full bg-navy-700 shrink-0" /><div><div>{e.text}</div><div className="text-[11px] text-slate-500">{fmtTime(e.at)}</div></div></li>
            ))}
          </ul>
          <div className="mt-3 text-sm rounded-lg bg-slate-50 border border-slate-200 p-2.5"><span className="font-semibold">Proof of delivery: </span>{s.pod_status}{s.pod_recipient ? ` (received by ${s.pod_recipient})` : ''}</div>
        </div>
        <MapView height={250} routes={[{ id: s.id, name: s.route_name, alternative: false, points: s.route_points }]}
          vehicles={s.last_reported_position ? [{ id: s.id, lat: s.last_reported_position.lat, lon: s.last_reported_position.lon, reported_at: s.last_reported_position.reported_at, confidence: s.data_confidence, bucket: 'ARRIVED_PENDING_POD' }] : []}
          caption="Latest reported position of the vehicle (simulated). Routes are illustrative." />
      </div>
    </div>
  )
}

function OrderDetail({ o, docs }: { o: CustomerOrder; docs: CustomerDocument[] }) {
  const late = o.updated_expected_delivery ? hoursBetween(o.updated_expected_delivery, o.promised_at) > 0 : false
  return (
    <Card title={`Order ${o.id} · ${o.product_code} · ${o.quantity_tonnes} t`} right={<span className="text-sm font-semibold text-navy-900">{o.status}</span>} className="" >
      <div data-testid="order-detail">
        <div className="grid sm:grid-cols-2 gap-3">
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3"><div className="label">Original promise</div><div className="text-xl font-bold">{fmtTime(o.promised_at)}</div></div>
          <div className="rounded-xl bg-navy-50 border border-navy-100 p-3"><div className="label">Updated expected delivery</div>
            <div className="text-xl font-bold">{o.updated_expected_delivery ? fmtEta(o.updated_expected_delivery) : o.status}</div>
            {o.updated_expected_delivery && <div className={`text-xs ${late ? 'text-red-700' : 'text-green-700'}`}>{late ? 'later than the original promise' : 'within the original promise'} · an estimate, not a guarantee</div>}
          </div>
        </div>
        {o.shipments.map((s) => <ShipmentView key={s.id} s={s} multi={o.shipments.length > 1} />)}
        <div className="mt-4"><CustomerOrderDocs orderId={o.id} shipments={o.shipments} docs={docs} /></div>
      </div>
    </Card>
  )
}

function Updates({ alerts }: { alerts: ReturnType<typeof useApi<CustomerAlert[]>> }) {
  const ack = async (id: number) => { await api(`/api/customer/me/alerts/${id}/acknowledge`, { method: 'POST' }); refreshAll() }
  return (
    <Card title="Delivery updates">
      <State loading={alerts.loading && !alerts.data} error={alerts.error} empty={!!alerts.data && alerts.data.length === 0} emptyText="No updates. Your deliveries are on plan." onRetry={alerts.reload} />
      <ul className="space-y-2">
        {alerts.data?.map((a) => (
          <li key={a.id} className={`rounded-lg border p-3 ${a.acknowledged ? 'bg-slate-50 border-slate-200' : 'bg-white border-amber-300'}`}>
            <div className="flex flex-wrap items-center gap-2">
              <strong className="text-sm">{a.title}</strong>
              {a.risk_level && <RiskBadge level={a.risk_level} prefix="Delay risk" />}
              <span className="text-xs text-slate-500 ml-auto">{fmtTime(a.created_sim_at)}</span>
            </div>
            <p className="text-sm mt-1">{a.message} {a.suggested_action}</p>
            {(a.promised_at || a.updated_expected_delivery) && (
              <p className="text-sm mt-1">Original promise: <strong>{fmtTime(a.promised_at)}</strong> · Updated expected delivery: <strong>{fmtEta(a.updated_expected_delivery)}</strong>{a.eta_from && a.eta_to ? ` (likely between ${fmtEta(a.eta_from)} and ${fmtEta(a.eta_to)})` : ''}</p>
            )}
            {!a.acknowledged ? <button className="btn-secondary mt-2" onClick={() => ack(a.id)}>Acknowledge</button> : <span className="text-xs text-slate-500">✓ Acknowledged</span>}
          </li>
        ))}
      </ul>
    </Card>
  )
}

function HistoryTab({ history }: { history: ReturnType<typeof useApi<CustomerHistory[]>> }) {
  return (
    <Card title="Delivery history">
      <State loading={history.loading && !history.data} error={history.error} empty={!!history.data && history.data.length === 0} emptyText="No completed deliveries yet." onRetry={history.reload} />
      {history.data && history.data.length > 0 && (
        <div className="overflow-x-auto"><table className="w-full">
          <thead><tr className="border-b border-slate-200"><th>Order</th><th>Product</th><th>Quantity</th><th>Promised</th><th>Arrived</th><th>Result</th><th>Proof of delivery</th></tr></thead>
          <tbody>{history.data.map((h) => (
            <tr key={h.shipment_id} className="border-b border-slate-100">
              <td className="font-semibold">{h.order_id}</td><td>{h.product_code}</td><td>{h.quantity_tonnes} t</td>
              <td className="text-xs">{fmtTime(h.promised_at)}</td><td className="text-xs">{fmtTime(h.arrived_at)}</td>
              <td><span className={`text-xs font-bold rounded px-1.5 py-0.5 ${h.on_time ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900'}`}>{h.on_time ? '✓ On time' : `▲ ${h.hours_vs_promise.toFixed(1)} h late`}</span></td>
              <td className="text-xs">{h.delivered_at ? `Signed ${fmtTime(h.delivered_at)}` : 'Awaiting'}</td>
            </tr>))}</tbody>
        </table></div>
      )}
    </Card>
  )
}

function DocumentsTab({ orders, docs }: { orders: CustomerOrder[]; docs: ReturnType<typeof useApi<CustomerDocument[]>> }) {
  const list = docs.data ?? []
  const invoices = list.filter((d) => d.kind === 'INVOICE').length
  const pods = list.filter((d) => d.kind === 'POD').length
  return (
    <div className="space-y-4">
      <div className="grid sm:grid-cols-2 gap-3">
        <div className="card p-4 flex items-center gap-3"><span className="h-11 w-11 rounded-xl bg-red-100 text-red-700 flex items-center justify-center"><Icon name="file" size={22} /></span><div><div className="text-2xl font-bold text-navy-900">{invoices}</div><div className="text-xs text-slate-600">invoices available</div></div></div>
        <div className="card p-4 flex items-center gap-3"><span className="h-11 w-11 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center"><Icon name="image" size={22} /></span><div><div className="text-2xl font-bold text-navy-900">{pods}</div><div className="text-xs text-slate-600">proofs of delivery available</div></div></div>
      </div>
      <State loading={docs.loading && !docs.data} error={docs.error} onRetry={docs.reload} />
      {orders.map((o) => (
        <Card key={o.id} title={`Order ${o.id} · ${o.product_code} · ${o.quantity_tonnes} t`} right={<Chip tone={o.status === 'Delivered' ? 'green' : 'blue'}>{o.status}</Chip>}>
          <CustomerOrderDocs orderId={o.id} shipments={o.shipments} docs={list} />
        </Card>
      ))}
      <p className="text-xs text-slate-500">Only documents for your own orders are shown. Every download is checked and logged.</p>
    </div>
  )
}

export default function CustomerPortal() {
  const orders = useApi<CustomerOrder[]>('/api/customer/me/orders')
  const alerts = useApi<CustomerAlert[]>('/api/customer/me/alerts')
  const history = useApi<CustomerHistory[]>('/api/customer/me/history')
  const docs = useApi<CustomerDocument[]>('/api/customer/me/documents')
  const [tab, setTab] = useState<'active' | 'history' | 'documents' | 'updates'>('active')
  const [sel, setSel] = useState<string | null>(null)
  const open = (orders.data ?? []).filter((o) => o.status !== 'Delivered')
  useEffect(() => { if (!sel && open.length) setSel(open[0].id) }, [open.length, sel])  // eslint-disable-line react-hooks/exhaustive-deps
  const current = open.find((o) => o.id === sel) ?? open[0]
  const inTransit = open.filter((o) => o.status === 'In transit').length
  const attention = open.filter((o) => o.shipments.some((s) => s.risk_level && s.risk_level !== 'Low')).length
  const unread = (alerts.data ?? []).filter((a) => !a.acknowledged).length

  return (
    <div className="space-y-4">
      <PageHeader title="My deliveries">Follow your orders from Plant X to your gate, download your invoices and proof of delivery, or ask the assistant. This page updates by itself.</PageHeader>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <Summary icon="box" label="Open orders" value={open.length} tone="bg-navy-100 text-navy-800" />
        <Summary icon="truck" label="In transit" value={inTransit} tone="bg-sky-100 text-sky-800" />
        <Summary icon="alert" label="Need your attention" value={attention} tone="bg-amber-100 text-amber-800" />
        <Summary icon="check" label="Delivered" value={history.data?.length ?? 0} tone="bg-emerald-100 text-emerald-800" />
      </div>

      <div className="flex flex-wrap gap-1 border-b border-slate-300" role="tablist" aria-label="Customer sections">
        {([['active', 'Active orders'], ['history', 'Delivery history'], ['documents', 'Documents'], ['updates', `Updates${unread ? ` (${unread})` : ''}`]] as const).map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={`px-3 py-2 text-sm font-semibold border-b-2 -mb-px ${tab === k ? 'border-navy-800 text-navy-900' : 'border-transparent text-slate-500 hover:text-navy-900'}`}>{label}</button>
        ))}
      </div>

      {tab === 'active' && (
        <>
          <State loading={orders.loading && !orders.data} error={orders.error} empty={!!orders.data && open.length === 0} emptyText="You have no open orders." onRetry={orders.reload} />
          {unread > 0 && alerts.data && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm flex items-center gap-3">
              <Icon name="bell" /><span className="flex-1"><strong>{alerts.data.find((a) => !a.acknowledged)?.title}</strong>: {alerts.data.find((a) => !a.acknowledged)?.message}</span>
              <button className="btn-secondary" onClick={() => setTab('updates')}>See updates</button>
            </div>
          )}
          {open.length > 0 && (
            <div className="grid lg:grid-cols-3 gap-4 items-start">
              <ul className="space-y-2" aria-label="Your orders">
                {open.map((o) => {
                  const risk = o.shipments.find((s) => s.risk_level && s.risk_level !== 'Low')?.risk_level
                  return (
                    <li key={o.id}>
                      <button onClick={() => setSel(o.id)} aria-pressed={current?.id === o.id}
                        className={`w-full text-left rounded-xl border p-3 ${current?.id === o.id ? 'border-navy-800 bg-white shadow' : 'border-slate-200 bg-white/70 hover:bg-white'}`}>
                        <div className="flex items-center justify-between gap-2"><span className="font-bold text-navy-900">{o.id}</span><span className="text-xs font-semibold text-slate-700">{o.status}</span></div>
                        <div className="text-xs text-slate-600">{o.product_code} · {o.quantity_tonnes} t</div>
                        <div className="text-xs text-slate-600 mt-1">Promised {fmtTime(o.promised_at)}</div>
                        <div className="text-xs mt-0.5">Expected <strong>{o.updated_expected_delivery ? fmtEta(o.updated_expected_delivery) : '-'}</strong></div>
                        {risk && <div className="mt-1.5"><RiskBadge level={risk} prefix="Delay risk" /></div>}
                      </button>
                    </li>
                  )
                })}
              </ul>
              <div className="lg:col-span-2">{current && <OrderDetail o={current} docs={docs.data ?? []} />}</div>
            </div>
          )}
        </>
      )}
      {tab === 'history' && <HistoryTab history={history} />}
      {tab === 'documents' && <DocumentsTab orders={orders.data ?? []} docs={docs} />}
      {tab === 'updates' && <Updates alerts={alerts} />}
      <ChatWidget orders={open.map((o) => ({ id: o.id }))} onOpenOrder={(id) => { setTab('active'); setSel(id) }} onOpenTab={(t) => setTab(t as typeof tab)} />
    </div>
  )
}
