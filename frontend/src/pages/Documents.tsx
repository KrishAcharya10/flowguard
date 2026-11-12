// Coordinator documents: invoice and proof-of-delivery status for every live order, with upload and verification.
import { useState } from 'react'
import { useApi, type DocumentsOverviewRow } from '../api/client'
import DocumentsPanel, { Chip, DownloadButton } from '../components/Documents'
import Icon from '../components/Icons'
import { Card, State } from '../components/ui'

export default function Documents() {
  const { data, error, loading, reload } = useApi<DocumentsOverviewRow[]>('/api/documents/overview')
  const [sel, setSel] = useState<string | null>(null)
  const rows = data ?? []
  const current = sel ?? rows[0]?.order_id ?? null
  const withInvoice = rows.filter((r) => r.invoice).length
  const podDone = rows.reduce((n, r) => n + r.pods_uploaded, 0)
  const podDue = rows.reduce((n, r) => n + r.pods_delivered, 0)

  return (
    <div className="space-y-4">
      <div className="rounded-2xl bg-gradient-to-r from-navy-900 via-navy-800 to-teal-800 text-white p-5 flex flex-wrap items-center gap-4">
        <span className="h-12 w-12 rounded-xl bg-white/15 flex items-center justify-center"><Icon name="file" size={26} /></span>
        <div><h1 className="text-2xl font-bold">Invoices and proof of delivery</h1>
          <p className="text-sm text-slate-200">Upload invoices against orders, review driver proof-of-delivery documents and verify them. Files are kept in private storage and every download is checked and logged.</p></div>
        <div className="ml-auto flex gap-5 text-center">
          <div><div className="text-2xl font-bold">{withInvoice}/{rows.length}</div><div className="text-[11px] uppercase tracking-wide text-slate-300">orders invoiced</div></div>
          <div><div className="text-2xl font-bold">{podDone}/{podDue}</div><div className="text-[11px] uppercase tracking-wide text-slate-300">delivered with POD</div></div>
        </div>
      </div>
      <State loading={loading && !data} error={error} empty={!!data && rows.length === 0} onRetry={reload} />
      {data && (
        <div className="grid xl:grid-cols-5 gap-4 items-start">
          <Card title={`Orders (${rows.length})`} className="xl:col-span-3">
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
