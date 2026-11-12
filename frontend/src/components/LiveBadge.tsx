import { useLive } from '../api/client'

/** "Live · updated 14:03:22": the time of the last successful change-check. Red if the server is unreachable. */
export default function LiveBadge({ dark = false }: { dark?: boolean }) {
  const { lastSync, online } = useLive()
  const time = lastSync ? new Date(lastSync).toLocaleTimeString('en-GB') : '…'
  const cls = online
    ? dark ? 'border-emerald-400/40 text-emerald-200' : 'border-emerald-300 bg-emerald-50 text-emerald-900'
    : dark ? 'border-red-400/50 text-red-200' : 'border-red-300 bg-red-50 text-red-900'
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold whitespace-nowrap ${cls}`}
      title="This screen checks for changes every few seconds and reloads its data only when something changed." role="status">
      <span className={`h-2 w-2 rounded-full ${online ? 'bg-emerald-500' : 'bg-red-500'}`} aria-hidden />
      {online ? `Live · updated ${time}` : 'Offline · retrying'}
    </span>
  )
}
