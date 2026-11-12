// Operational activity feed. Every row is a stored backend record (event, alert, prediction or audit row);
// nothing is generated in the browser. New rows are tagged for a few seconds so changes are easy to spot.
import { useEffect, useRef, useState } from 'react'
import { useApi, type Activity } from '../api/client'
import { fmtTime } from '../lib/format'
import Icon from './Icons'
import { State } from './ui'

const ICON: Record<string, string> = {
  MILESTONE: 'truck', POSITION: 'map', ASSIGNED: 'box', REPORT: 'wrench', DISRUPTION: 'alert', INTERVENTION: 'check',
  ALERT: 'bell', NOTIFICATION: 'bell', RISK: 'activity', ETA: 'clock', AUDIT: 'shield', ORDER: 'plus',
}
const TONE: Record<string, string> = {
  info: 'bg-slate-100 text-slate-700', ok: 'bg-emerald-100 text-emerald-800', warn: 'bg-amber-100 text-amber-800', alert: 'bg-red-100 text-red-800',
}
const SOURCE: Record<string, string> = { DRIVER: 'driver', SIMULATED: 'simulated', COORDINATOR: 'coordinator', ENGINE: 'engine', SYSTEM: 'system' }

export default function ActivityFeed({ limit = 40, onSelect, height = 560 }: { limit?: number; onSelect?: (shipmentId: string) => void; height?: number }) {
  const { data, error, loading, reload } = useApi<Activity[]>(`/api/activity?limit=${limit}`)
  const seen = useRef<Set<string> | null>(null)
  const [fresh, setFresh] = useState<Set<string>>(new Set())

  useEffect(() => {
    if (!data) return
    const ids = new Set(data.map((d) => d.id))
    if (seen.current !== null) {
      const added = [...ids].filter((i) => !seen.current!.has(i))
      if (added.length) {
        setFresh(new Set(added))
        const t = window.setTimeout(() => setFresh(new Set()), 6000)
        seen.current = ids
        return () => window.clearTimeout(t)
      }
    }
    seen.current = ids
  }, [data])

  return (
    <div>
      <State loading={loading && !data} error={error} empty={!!data && data.length === 0} emptyText="No activity yet." onRetry={reload} />
      <ul className="overflow-y-auto pr-1 space-y-1.5" style={{ maxHeight: height }} aria-label="Operational activity">
        {data?.map((a) => (
          <li key={a.id} className={`rounded-lg border px-2.5 py-2 flex gap-2.5 ${fresh.has(a.id) ? 'border-navy-700 bg-navy-50' : 'border-slate-200 bg-white'}`}>
            <span className={`h-7 w-7 shrink-0 rounded-full flex items-center justify-center ${TONE[a.severity]}`}><Icon name={ICON[a.kind] ?? 'activity'} size={14} /></span>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div className="text-[13px] font-semibold leading-snug text-slate-900">{a.title}{fresh.has(a.id) && <span className="ml-1.5 rounded bg-navy-800 text-white text-[9px] px-1 py-0.5 align-middle">NEW</span>}</div>
              </div>
              {a.detail && <div className="text-xs text-slate-600 line-clamp-2">{a.detail}</div>}
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[11px] text-slate-500">
                <span>{fmtTime(a.at)}</span>
                <span>· {SOURCE[a.source] ?? a.source.toLowerCase()}</span>
                {a.shipment_id && onSelect && <button className="underline text-navy-700" onClick={() => onSelect(a.shipment_id!)}>open {a.shipment_id}</button>}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  )
}
