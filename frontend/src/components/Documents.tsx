// Invoice and proof-of-delivery components shared by the three portals.
// Files are uploaded as the raw request body and downloaded through an authenticated, ownership-checked endpoint.
import { useRef, useState } from 'react'
import { api, downloadDocument, refreshAll, uploadFile, useApi, type CustomerDocument, type DocumentRow, type OrderDocuments } from '../api/client'
import { fmtTime } from '../lib/format'
import Icon from './Icons'
import { Notice, State } from './ui'

export const MAX_MB = 10
const OK_EXT = ['pdf', 'jpg', 'jpeg', 'png']

export const size = (b: number) => (b >= 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`)

/** File picker with a drop area. The server is the real judge of type and size (it checks the file content). */
export function FileDrop({ file, onFile, label = 'Choose a PDF, JPG or PNG' }: { file: File | null; onFile: (f: File | null) => void; label?: string }) {
  const input = useRef<HTMLInputElement>(null)
  const [err, setErr] = useState('')
  const [over, setOver] = useState(false)
  const take = (f: File | undefined) => {
    setErr('')
    if (!f) return onFile(null)
    const ext = f.name.split('.').pop()?.toLowerCase() ?? ''
    if (!OK_EXT.includes(ext)) { setErr('Only PDF, JPG, JPEG and PNG files are accepted.'); return onFile(null) }
    if (f.size > MAX_MB * 1048576) { setErr(`This file is larger than ${MAX_MB} MB.`); return onFile(null) }
    onFile(f)
  }
  return (
    <div>
      <div
        onDragOver={(e) => { e.preventDefault(); setOver(true) }} onDragLeave={() => setOver(false)}
        onDrop={(e) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files[0]) }}
        className={`rounded-xl border-2 border-dashed p-4 text-center transition-colors ${over ? 'border-navy-700 bg-navy-50' : file ? 'border-emerald-400 bg-emerald-50' : 'border-slate-300 bg-slate-50 hover:bg-white'}`}>
        <input ref={input} type="file" className="sr-only" aria-label="Document file" accept=".pdf,.jpg,.jpeg,.png,application/pdf,image/png,image/jpeg" onChange={(e) => take(e.target.files?.[0])} />
        {file ? (
          <div className="flex items-center justify-center gap-2 text-sm"><Icon name={file.type === 'application/pdf' ? 'file' : 'image'} className="text-emerald-700" /><strong className="truncate max-w-[16rem]">{file.name}</strong><span className="text-slate-500">{size(file.size)}</span>
            <button type="button" className="underline text-navy-700" onClick={() => { onFile(null); if (input.current) input.current.value = '' }}>remove</button></div>
        ) : (
          <button type="button" className="inline-flex flex-col items-center gap-1 text-sm text-slate-700" onClick={() => input.current?.click()}>
            <span className="h-10 w-10 rounded-full bg-navy-100 text-navy-800 flex items-center justify-center"><Icon name="upload" size={20} /></span>
            <span className="font-semibold">{label}</span><span className="text-xs text-slate-500">or drop it here · up to {MAX_MB} MB</span>
          </button>
        )}
      </div>
      {err && <p className="text-xs text-red-700 mt-1" role="alert">{err}</p>}
    </div>
  )
}

export function Chip({ tone, children }: { tone: 'green' | 'amber' | 'red' | 'blue' | 'slate'; children: React.ReactNode }) {
  const c = { green: 'bg-emerald-100 text-emerald-900 border-emerald-300', amber: 'bg-amber-100 text-amber-900 border-amber-300', red: 'bg-red-100 text-red-900 border-red-300', blue: 'bg-sky-100 text-sky-900 border-sky-300', slate: 'bg-slate-100 text-slate-700 border-slate-300' }[tone]
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-bold whitespace-nowrap ${c}`}>{children}</span>
}

export function DownloadButton({ id, name, label = 'Download' }: { id: number; name: string; label?: string }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  return (
    <span>
      <button className="btn-secondary !py-1 !px-2.5 !text-xs" disabled={busy} onClick={async () => { setBusy(true); setErr(''); try { await downloadDocument(id, name) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) } }}>
        <Icon name="download" size={14} />{busy ? 'Preparing…' : label}
      </button>
      {err && <span className="ml-2 text-xs text-red-700" role="alert">{err}</span>}
    </span>
  )
}

function DocLine({ d, extra }: { d: DocumentRow; extra?: React.ReactNode }) {
  const pdf = d.content_type === 'application/pdf'
  return (
    <div className={`flex flex-wrap items-center gap-3 rounded-xl border p-3 ${d.is_current ? 'border-slate-200 bg-white' : 'border-slate-200 bg-slate-50 opacity-80'}`}>
      <span className={`h-11 w-11 shrink-0 rounded-lg flex items-center justify-center ${pdf ? 'bg-red-100 text-red-700' : 'bg-sky-100 text-sky-700'}`}><Icon name={pdf ? 'file' : 'image'} size={22} /></span>
      <div className="min-w-0 flex-1">
        <div className="font-semibold text-sm truncate" title={d.original_filename}>{d.original_filename}</div>
        <div className="text-xs text-slate-500">
          {d.kind === 'INVOICE' ? `${d.invoice_number ?? 'Invoice'} · ` : ''}version {d.version} · {size(d.size_bytes)} · uploaded {fmtTime(d.uploaded_sim_at)} by {d.uploaded_by_name.replace(' (fictional)', '')}
        </div>
        {d.recipient_name && <div className="text-xs text-slate-500">Received by {d.recipient_name}{d.delivered_sim_at ? ` · delivered ${fmtTime(d.delivered_sim_at)}` : ''}</div>}
        {d.replace_reason && <div className="text-xs text-slate-500">Reason for replacing: {d.replace_reason}</div>}
      </div>
      <Chip tone={d.status === 'VERIFIED' ? 'green' : d.status === 'SUPERSEDED' ? 'slate' : 'blue'}>{d.status === 'VERIFIED' ? '✓ Verified' : d.status === 'SUPERSEDED' ? 'Replaced' : d.status === 'ISSUED' ? 'Issued' : 'Uploaded'}</Chip>
      <DownloadButton id={d.id} name={d.original_filename} />
      {extra}
    </div>
  )
}

const POD_TEXT: Record<string, [string, 'green' | 'amber' | 'slate' | 'blue']> = {
  NOT_DELIVERED: ['Not delivered yet', 'slate'], AWAITING_POD: ['Arrived · awaiting driver upload', 'amber'],
  NO_DOCUMENT: ['Delivered · no document', 'amber'], UPLOADED: ['Document uploaded', 'blue'], VERIFIED: ['Verified', 'green'],
}

/** Coordinator: finish a delivery on the driver's behalf (the driver cannot, or forgot), or add the missing document. */
function OnBehalf({ shipmentId, delivered, recipient }: { shipmentId: string; delivered: boolean; recipient?: string | null }) {
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState(recipient ?? '')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const ok = name.trim().length >= 2
  const run = async (fn: () => Promise<unknown>, text: string) => {
    setBusy(true)
    setMsg(null)
    try { await fn(); setMsg({ kind: 'ok', text }); setFile(null); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  return (
    <div className="rounded-xl border-2 border-amber-400 bg-amber-50 p-3 space-y-2" data-testid={`on-behalf-${shipmentId}`}>
      <div className="text-sm font-bold text-amber-950">{delivered ? 'Add the missing proof-of-delivery document' : 'The vehicle has arrived. Complete the delivery for the driver'}</div>
      {!delivered && <p className="text-xs text-amber-950">Use this if the driver cannot do it on the phone. It is recorded as done by the control tower.</p>}
      <label className="block text-xs font-medium text-slate-700">Who received the delivery?<input className="input mt-1" value={name} maxLength={80} onChange={(e) => setName(e.target.value)} placeholder="Receiver's full name" /></label>
      <FileDrop file={file} onFile={setFile} label="Choose the signed note or photo" />
      <div className="flex flex-wrap gap-2">
        <button className="btn-primary" disabled={busy || !ok || !file} onClick={() => run(() => uploadFile(`/api/shipments/${shipmentId}/pod-document?${new URLSearchParams({ filename: file!.name, recipient_name: name.trim() })}`, file!), delivered ? 'Document added.' : 'Delivery completed with the document.')}><Icon name="upload" size={16} />{delivered ? 'Add document' : 'Upload and complete delivery'}</button>
        {!delivered && <button className="btn-secondary" disabled={busy || !ok} onClick={() => run(() => api(`/api/shipments/${shipmentId}/complete-delivery`, { method: 'POST', body: { recipient_name: name.trim() } }), 'Delivery completed without a document.')}>Complete without a document</button>}
      </div>
      {!ok && <p className="text-xs text-amber-900">Enter the receiver's name to continue.</p>}
      {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
    </div>
  )
}

/** Coordinator: manage the invoice and proof-of-delivery documents of one order. */
export default function DocumentsPanel({ orderId }: { orderId: string }) {
  const { data, error, loading, reload } = useApi<OrderDocuments>(`/api/orders/${orderId}/documents`)
  const [file, setFile] = useState<File | null>(null)
  const [number, setNumber] = useState('')
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'error'; text: string } | null>(null)
  const [verifying, setVerifying] = useState<number | null>(null)
  const [match, setMatch] = useState(false)
  if (!data) return <State loading={loading} error={error} onRetry={reload} />
  const current = data.invoices.find((d) => d.is_current)

  const send = async () => {
    if (!file) return
    setBusy(true)
    setMsg(null)
    try {
      const q = new URLSearchParams({ filename: file.name, ...(number.trim() ? { invoice_number: number.trim() } : {}), ...(current ? { reason: reason.trim() } : {}) })
      const r = await uploadFile<{ message: string }>(`/api/orders/${orderId}/invoice?${q}`, file)
      setMsg({ kind: 'ok', text: `${r.message} The customer has been notified.` })
      setFile(null); setNumber(''); setReason('')
      refreshAll()
    } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }
  const verify = async (id: number) => {
    setBusy(true)
    try { await api(`/api/documents/${id}/verify`, { method: 'POST' }); setVerifying(null); setMatch(false); refreshAll() } catch (e) { setMsg({ kind: 'error', text: (e as Error).message }) } finally { setBusy(false) }
  }

  return (
    <div className="space-y-5" data-testid="documents-panel">
      <section>
        <h3 className="label mb-2">Invoice · {data.customer_name.replace(' (fictional)', '')}</h3>
        {current ? <DocLine d={current} /> : <p className="text-sm text-slate-600 rounded-xl border border-dashed border-slate-300 p-3">No invoice has been uploaded for this order yet.</p>}
        <div className="mt-3 rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
          <div className="text-sm font-semibold">{current ? 'Replace the invoice with a new version' : 'Upload the invoice'}</div>
          <FileDrop file={file} onFile={setFile} label={current ? 'Choose the corrected invoice' : 'Choose the invoice file'} />
          <div className="grid sm:grid-cols-2 gap-2">
            <label className="text-xs font-medium text-slate-700">Invoice number (optional)<input className="input mt-1" value={number} maxLength={40} onChange={(e) => setNumber(e.target.value)} placeholder="INV-2026-0001" /></label>
            {current && <label className="text-xs font-medium text-slate-700">Reason for replacing (required)<input className="input mt-1" value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="e.g. wrong quantity" /></label>}
          </div>
          <button className="btn-primary" disabled={!file || busy || (!!current && reason.trim().length < 5)} onClick={send}><Icon name="upload" size={16} />{busy ? 'Uploading…' : current ? 'Replace invoice (new version)' : 'Upload invoice'}</button>
          {msg && <Notice kind={msg.kind}>{msg.text}</Notice>}
        </div>
        {data.invoices.length > 1 && (
          <details className="mt-2"><summary className="text-sm text-navy-700 cursor-pointer">Version history ({data.invoices.length})</summary>
            <div className="space-y-2 mt-2">{data.invoices.filter((d) => !d.is_current).map((d) => <DocLine key={d.id} d={d} />)}</div></details>
        )}
      </section>

      <section>
        <h3 className="label mb-2">Proof of delivery</h3>
        <div className="space-y-3">
          {data.shipments.map((sh) => {
            const [text, tone] = POD_TEXT[sh.pod_status]
            const cur = sh.documents.find((d) => d.is_current)
            return (
              <div key={sh.shipment_id} className="rounded-xl border border-slate-200 p-3 space-y-2">
                <div className="flex flex-wrap items-center gap-2"><strong className="text-sm">{sh.shipment_id}</strong><span className="text-xs text-slate-500">{sh.quantity_tonnes} t · {sh.state_label}</span><Chip tone={tone}>{text}</Chip></div>
                {(sh.pod_status === 'AWAITING_POD' || sh.pod_status === 'NO_DOCUMENT') && <OnBehalf shipmentId={sh.shipment_id} delivered={sh.pod_status === 'NO_DOCUMENT'} recipient={sh.recipient_name} />}
                {sh.documents.length === 0 && sh.pod_status !== 'AWAITING_POD' && sh.pod_status !== 'NO_DOCUMENT' && <p className="text-xs text-slate-500">{sh.pod_status === 'NOT_DELIVERED' ? 'The driver uploads the signed document after the vehicle reaches the customer gate.' : 'No document has been uploaded yet.'}</p>}
                {sh.documents.map((d) => (
                  <DocLine key={d.id} d={d} extra={d.is_current && d.status === 'UPLOADED' && (
                    verifying === d.id ? (
                      <div className="basis-full rounded-lg bg-amber-50 border border-amber-300 p-2 space-y-2">
                        <label className="text-sm flex items-start gap-2"><input type="checkbox" className="mt-1" checked={match} onChange={(e) => setMatch(e.target.checked)} />I checked that this document belongs to <strong>{sh.shipment_id}</strong> (order {data.order_id}) and the recipient name <strong>{d.recipient_name}</strong> is plausible.</label>
                        <div className="flex gap-2"><button className="btn-primary !py-1" disabled={!match || busy} onClick={() => verify(d.id)}>Confirm verification</button><button className="btn-secondary !py-1" onClick={() => { setVerifying(null); setMatch(false) }}>Cancel</button></div>
                      </div>
                    ) : <button className="btn-secondary !py-1 !px-2.5 !text-xs" onClick={() => { setVerifying(d.id); setMatch(false) }}><Icon name="check" size={14} />Verify</button>
                  )} />
                ))}
                {cur === undefined && sh.documents.length > 0 && <p className="text-xs text-slate-500">All versions were replaced.</p>}
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}

/** Customer: availability and download of own invoice and proof of delivery for one order. */
export function CustomerOrderDocs({ orderId, shipments, docs }: { orderId: string; shipments: { id: string; state: string; quantity_tonnes: number }[]; docs: CustomerDocument[] }) {
  const inv = docs.find((d) => d.kind === 'INVOICE' && d.order_id === orderId)
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 space-y-2" data-testid="order-documents">
      <div className="label">Documents</div>
      <CustomerDocRow icon="file" title="Invoice" doc={inv} missing="Not issued yet" />
      {shipments.map((sh) => {
        const pod = docs.find((d) => d.kind === 'POD' && d.shipment_id === sh.id)
        return <CustomerDocRow key={sh.id} icon="image" title={`Proof of delivery${shipments.length > 1 ? ` · ${sh.id} (${sh.quantity_tonnes} t)` : ''}`} doc={pod}
          missing={sh.state === 'DELIVERED' ? 'Delivered · signed document not uploaded yet' : sh.state === 'ARRIVED_AT_CUSTOMER_GATE' ? 'Arrived · awaiting signature' : 'Available after delivery'} />
      })}
    </div>
  )
}

function CustomerDocRow({ icon, title, doc, missing }: { icon: string; title: string; doc?: CustomerDocument; missing: string }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <span className={`h-9 w-9 shrink-0 rounded-lg flex items-center justify-center ${doc ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-500'}`}><Icon name={icon} size={18} /></span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">{title}</div>
        <div className="text-xs text-slate-500">{doc ? `${doc.filename} · ${size(doc.size_bytes)} · uploaded ${fmtTime(doc.uploaded_at)}${doc.recipient_name ? ` · received by ${doc.recipient_name}` : ''}` : missing}</div>
      </div>
      {doc ? <><Chip tone="green">✓ Available</Chip><DownloadButton id={doc.id} name={doc.filename} /></> : <Chip tone="slate">Not yet available</Chip>}
    </div>
  )
}
