// Shared UI pieces. Status is never shown by colour alone: every badge has an icon and a text label.
import type { ReactNode } from 'react'
import type { Milestone } from '../api/client'
import { fmtTime } from '../lib/format'

const RISK: Record<string, { cls: string; icon: string; label: string }> = {
  LOW: { cls: 'bg-green-100 text-green-900 border-green-300', icon: '✓', label: 'Low' },
  MEDIUM: { cls: 'bg-amber-100 text-amber-900 border-amber-300', icon: '▲', label: 'Medium' },
  HIGH: { cls: 'bg-red-100 text-red-900 border-red-300', icon: '●', label: 'High' },
  CRITICAL: { cls: 'bg-red-700 text-white border-red-800', icon: '■', label: 'Critical' },
  INFO: { cls: 'bg-blue-100 text-blue-900 border-blue-300', icon: 'i', label: 'Info' },
}
const BUCKET: Record<string, { cls: string; icon: string; label: string }> = {
  LATE: { cls: 'bg-red-100 text-red-900 border-red-300', icon: '●', label: 'Late' },
  AT_RISK: { cls: 'bg-amber-100 text-amber-900 border-amber-300', icon: '▲', label: 'At risk' },
  ON_TRACK: { cls: 'bg-green-100 text-green-900 border-green-300', icon: '✓', label: 'On track' },
  ARRIVED_PENDING_POD: { cls: 'bg-blue-100 text-blue-900 border-blue-300', icon: '◆', label: 'Arrived, POD pending' },
  DELIVERED: { cls: 'bg-slate-100 text-slate-800 border-slate-300', icon: '✓', label: 'Delivered' },
  SPLIT_PARENT: { cls: 'bg-slate-100 text-slate-600 border-slate-300', icon: '⑂', label: 'Split parent' },
}

export function Pill({ cls, children }: { cls: string; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold whitespace-nowrap ${cls}`}>{children}</span>
}

export function RiskBadge({ level, prefix = 'Risk' }: { level?: string | null; prefix?: string }) {
  if (!level) return <span className="text-slate-400 text-xs">-</span>
  const r = RISK[level.toUpperCase()] ?? RISK.INFO
  return <Pill cls={r.cls}><span aria-hidden>{r.icon}</span>{prefix ? `${prefix}: ` : ''}{r.label}</Pill>
}

export function BucketBadge({ bucket }: { bucket: string }) {
  const b = BUCKET[bucket] ?? BUCKET.DELIVERED
  return <Pill cls={b.cls}><span aria-hidden>{b.icon}</span>{b.label}</Pill>
}

export function ConfidenceBadge({ value }: { value?: string | null }) {
  if (!value) return null
  const cls = value === 'STALE' ? 'bg-amber-100 text-amber-900 border-amber-300' : value === 'AGING' ? 'bg-slate-100 text-slate-800 border-slate-300' : 'bg-green-50 text-green-900 border-green-200'
  const icon = value === 'STALE' ? '⚠' : value === 'AGING' ? '◔' : '✓'
  return <Pill cls={cls}><span aria-hidden>{icon}</span>Data: {value.charAt(0) + value.slice(1).toLowerCase()}</Pill>
}

export function Card({ title, right, children, className = '' }: { title?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card p-4 ${className}`}>
      {(title || right) && (
        <div className="flex items-start justify-between gap-2 mb-3">
          {title && <h2 className="text-sm font-bold text-navy-900">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Kpi({ label, value, sub }: { label: string; value: ReactNode; sub?: ReactNode }) {
  return (
    <div className="card p-3">
      <div className="label">{label}</div>
      <div className="text-2xl font-bold text-navy-900 mt-1">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-0.5">{sub}</div>}
    </div>
  )
}

/** Loading, error and empty states for every data view. */
export function State({ loading, error, empty, emptyText = 'Nothing to show yet.', onRetry }: {
  loading?: boolean; error?: string | null; empty?: boolean; emptyText?: string; onRetry?: () => void
}) {
  if (error) {
    return (
      <div role="alert" className="rounded-md border border-red-300 bg-red-50 text-red-900 text-sm p-3 flex items-center justify-between gap-2">
        <span><strong>Could not load.</strong> {error}</span>
        {onRetry && <button className="btn-secondary" onClick={onRetry}>Retry</button>}
      </div>
    )
  }
  if (loading) return <div className="text-sm text-slate-500 p-3" aria-live="polite">Loading…</div>
  if (empty) return <div className="text-sm text-slate-500 p-3">{emptyText}</div>
  return null
}

export function Notice({ kind = 'info', children }: { kind?: 'info' | 'warn' | 'error' | 'ok'; children: ReactNode }) {
  const cls = { info: 'border-blue-200 bg-blue-50 text-blue-900', warn: 'border-amber-300 bg-amber-50 text-amber-900', error: 'border-red-300 bg-red-50 text-red-900', ok: 'border-green-300 bg-green-50 text-green-900' }[kind]
  return <div role={kind === 'error' ? 'alert' : 'status'} className={`rounded-md border text-sm p-3 ${cls}`}>{children}</div>
}

export function MilestoneBar({ items }: { items: Milestone[] }) {
  return (
    <ol className="flex flex-wrap gap-y-2" aria-label="Status milestones">
      {items.map((m, i) => (
        <li key={m.state} className="flex items-center">
          <div className="flex flex-col items-center w-28 text-center">
            <span className={`h-7 w-7 rounded-full border-2 flex items-center justify-center text-xs font-bold ${m.current ? 'bg-navy-800 border-navy-800 text-white' : m.done ? 'bg-green-600 border-green-600 text-white' : 'bg-white border-slate-300 text-slate-400'}`}>
              {m.done && !m.current ? '✓' : i + 1}
            </span>
            <span className={`text-[11px] leading-tight mt-1 ${m.current ? 'font-bold text-navy-900' : m.done ? 'text-slate-700' : 'text-slate-400'}`}>{m.label}{m.current ? ' (now)' : ''}</span>
            <span className="text-[10px] text-slate-500">{m.occurred_at ? fmtTime(m.occurred_at) : m.done ? 'done' : 'pending'}</span>
          </div>
          {i < items.length - 1 && <span className={`h-0.5 w-4 -mt-8 ${items[i + 1].done ? 'bg-green-600' : 'bg-slate-300'}`} aria-hidden />}
        </li>
      ))}
    </ol>
  )
}

export function Modelled({ children }: { children?: ReactNode }) {
  return <span className="inline-block rounded bg-slate-800 text-white text-[10px] font-bold px-1.5 py-0.5 tracking-wide">{children ?? 'MODELLED'}</span>
}
