// Coordinator documents: invoice and proof-of-delivery status for every live order, with upload and verification.
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useApi, type DocumentsOverviewRow } from '../api/client'
import DocumentsPanel, { Chip, DownloadButton } from '../components/Documents'
import Icon from '../components/Icons'
import { Card, PageHeader, State } from '../components/ui'

export default function Documents() {
  const { data, error, loading, reload } = useApi<DocumentsOverviewRow[]>('/api/documents/overview')
  const [params] = useSearchParams()
  const [sel, setSel] = useState<string | null>(params.get('order'))
  const [onlyAwaiting, setOnlyAwaiting] = useState(false)
  const all = data ?? []
  const awaiting = all.filter((r) => r.shipment_states.includes('ARRIVED_AT_CUSTOMER_GATE'))
  const rows = onlyAwaiting ? awaiting : all
  const current = sel ?? rows[0]?.order_id ?? null
  const withInvoice = rows.filter((r) => r.invoice).length
  const podDone = rows.reduce((n, r) => n + r.pods_uploaded, 0)
  const podDue = rows.reduce((n, r) => n + r.pods_delivered, 0)

  return (
    <div className="space-y-4">
      <PageHeader icon={<Icon name="file" size={22} />} title="Invoices and proof of delivery" right={<div className="flex gap-6 text-right"><div><div className="text-xl font-bold text-navy-900 tabular-nums">{withInvoice}/{rows.length}</div><div className="label !text-[10px]">orders invoiced</div></div><div><div className="text-xl font-bold text-navy-900 tabular-nums">{podDone}/{podDue}</div><div className="label !text-[10px]">delivered with POD</div></div></div>}>Upload invoices against orders, review driver proof-of-delivery documents and verify them. Files are kept in private storage and every download is checked and logged.</PageHeader>
      {awaiting.length > 0 && (
        <div className="rounded-xl border-2 border-amber-400 bg-amber-50 p-3 flex flex-wrap items-center gap-3">
          <span className="text-sm text-amber-950"><strong>{awaiting.length} delivered load{awaiting.length > 1 ? 's are' : ' is'} waiting for proof of delivery.</strong> The vehicle has arrived but the delivery is not finished. Open the order and complete it for the driver, or ask the driver to do it in the driver app.</span>
          <button className="btn-primary ml-auto" onClick={() => { setOnlyAwaiting(!onlyAwaiting); setSel(null) }}>{onlyAwaiting ? 'Show all orders' : 'Show only these'}</button>
        </div>
      )}
      <State loading={loading && !data} error={error} empty={!!data && rows.length === 0} onRetry={reload} />
      {data && (
        <div className="grid xl:grid-cols-5 gap-4 items-start">
          <Card title={`Orders (${rows.length}${onlyAwaiting ? ', awaiting proof of delivery' : ''})`} className="xl:col-span-3">
            <div className="overflow-x-auto"><table className="w-full">
              <thead><tr className="border-b border-slate-200"><th>Order</th><th>Customer</th><th>Invoice</th><th>Proof of delivery</th><th></th></tr></thead>
              <tbody>{rows.map((r) => (
                <tr key={r.order_id} className={`border-b border-slate-100 cursor-pointer hover:bg-navy-50 ${current === r.order_id ? 'bg-navy-50' : ''}`} onClick={() => setSel(r.order_id)} data-testid={`doc-row-${r.order_id}`}>
                  <td className="font-semibold">{r.order_id}<div className="text-xs font-normal text-slate-500">{r.product_code} · {r.quantity_tonnes} t</div></td>
                  <td className="text-xs">{r.customer_name.replace(' (fictional)', '')}</td>
                  <td>{r.invoice ? <div className="flex flex-col gap-1 items-start"><Chip tone="green">✓ v{r.invoice.version} · {r.invoice.invoice_number}</Chip><span onClick={(e) => e.stopPropagation()}><DownloadButton id={r.invoice.id} name={r.invoice.original_filename} /></span></div> : <Chip tone="amber">Not uploaded</Chip>}</td>
                  <td className="text-xs">{r.pods_delivered === 0 ? <Chip tone="slate">Not delivered yet</Chip> : <Chip tone={r.pods_verified === r.pods_delivered ? 'green' : r.pods_uploaded === r.pods_delivered ? 'blue' : 'amber'}>{r.pods_uploaded}/{r.pods_delivered} uploaded · {r.pods_verified} verified</Chip>}</td>
                  <td><button className="btn-secondary !py-1 !px-2.5 !text-xs" aria-label={`Manage documents for ${r.order_id}`} onClick={() => setSel(r.order_id)}>Manage</button></td>
                </tr>))}</tbody>
            </table></div>
          </Card>
          <Card title={current ? `Documents · ${current}` : 'Documents'} className="xl:col-span-2">
            {current ? <DocumentsPanel orderId={current} /> : <State empty emptyText="Choose an order." />}
          </Card>
        </div>
      )}
    </div>
  )
}
