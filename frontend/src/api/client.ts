// API client. Types are GENERATED from contracts/openapi.json (npm run types) - never written by hand.
import { useCallback, useEffect, useState } from 'react'
import type { components } from './schema'

type S = components['schemas']
export type User = S['UserOut']
export type Shipment = S['ShipmentOut']
export type ShipmentDetail = S['ShipmentDetailOut']
export type Prediction = S['PredictionOut']
export type Milestone = S['MilestoneOut']
export type ControlTower = S['ControlTowerOut']
export type MapData = S['MapDataOut']
export type Alert = S['AlertOut']
export type CaseOut = S['CaseOut']
export type Scenario = S['ScenarioOut']
export type Disruption = S['DisruptionOut']
export type ReferenceData = S['ReferenceDataOut']
export type CustomerOrder = S['CustomerOrderOut']
export type CustomerShipment = S['CustomerShipmentOut']
export type CustomerAlert = S['CustomerAlertOut']
export type CustomerHistory = S['CustomerHistoryItem']
export type DriverShipment = S['DriverShipmentOut']
export type DriverHistory = S['DriverHistoryItem']
export type AnalyticsOverview = S['AnalyticsOverviewOut']
export type DimensionRow = S['DimensionRow']
export type DelayCauses = S['DelayCausesOut']
export type BusinessImpact = S['BusinessImpactOut']
export type AssumptionsOut = S['AssumptionsOut']
export type Assumptions = S['Assumptions']
export type AuditRow = S['AuditOut']
export type EventRow = S['EventOut']
export type Clock = S['ClockOut']
export type Activity = S['ActivityOut']
export type OrderCreated = S['OrderCreatedOut']
export type Slot = S['SlotOut']
export type Booking = S['BookingOut']
export type GateOverview = S['GateOverviewOut']
export type GateSummary = S['GateSummaryOut']
export type DriverBooking = S['DriverBookingOut']
export type DocumentRow = S['DocumentOut']
export type OrderDocuments = S['OrderDocumentsOut']
export type DocumentsOverviewRow = S['DocumentsOverviewRow']
export type CustomerDocument = S['CustomerDocumentOut']
export type ChatReply = S['ChatReplyOut']

// Token lives in sessionStorage: one login per browser tab (see docs/KNOWN_LIMITATIONS.md for the XSS trade-off).
const KEY = 'flowguard.session'

export function getSession(): { token: string; user: User } | null {
  try {
    const raw = sessionStorage.getItem(KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}
export function setSession(s: { token: string; user: User } | null) {
  if (s) sessionStorage.setItem(KEY, JSON.stringify(s))
  else sessionStorage.removeItem(KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

export async function api<T>(path: string, init?: { method?: string; body?: unknown; raw?: File }): Promise<T> {
  const session = getSession()
  const send = async () => {
    try {
      return await fetch(path, {
        method: init?.method ?? 'GET',
        cache: 'no-store',
        headers: {
          ...(init?.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
          ...(init?.raw ? { 'Content-Type': init.raw.type || 'application/octet-stream' } : {}),
          ...(session ? { Authorization: `Bearer ${session.token}` } : {}),
        },
        body: init?.raw ?? (init?.body !== undefined ? JSON.stringify(init.body) : undefined),
      })
    } catch {
      throw new ApiError(0, 'Cannot reach the FlowGuard server. Is it running?')
    }
  }
  let res = await send()
  // While the demo data is being rebuilt (reset / "Jump"), the database is empty for a few seconds and the
  // user briefly "does not exist". Confirm a 401 for ~5 s before ending the session, so a rebuild never logs anyone out.
  for (let i = 0; i < 5 && res.status === 401 && session && init?.method !== 'POST'; i++) {
    await sleep(1000)
    res = await send()
  }
  if (res.status === 401 && session) {
    setSession(null)
    window.location.assign('/login')
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') msg = j.detail
      else if (Array.isArray(j.detail)) msg = j.detail.map((d: { loc?: string[]; msg: string }) => `${d.loc?.slice(1).join('.') ?? ''}: ${d.msg}`).join('; ')
    } catch { /* keep default */ }
    throw new ApiError(res.status, msg)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------------------------------------
// Refresh signal: any mutation, and the live-sync poller, call refreshAll(); every useApi hook then reloads.
const listeners = new Set<() => void>()
export function refreshAll() {
  listeners.forEach((l) => l())
}

export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState<boolean>(!!path)
  const [n, setN] = useState(0)
  const reload = useCallback(() => setN((x) => x + 1), [])
  useEffect(() => {
    listeners.add(reload)
    return () => { listeners.delete(reload) }
  }, [reload])
  useEffect(() => {
    if (!path) return
    let alive = true
    setLoading(true)
    api<T>(path)
      .then((d) => {
        if (!alive) return
        // keep the old object when nothing changed: no needless re-render, no map redraw, no flicker
        setData((prev) => (prev !== null && JSON.stringify(prev) === JSON.stringify(d) ? prev : d))
        setError(null)
      })
      .catch((e: Error) => { if (alive) setError(e.message) })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [path, n])
  return { data, error, loading, reload }
}

// ---------------------------------------------------------------------------------------------------------
// Live sync: every open screen polls ONE cheap endpoint (a hashed change-stamp). Data is reloaded only when
// the stamp changes, so a quiet system makes one tiny request every few seconds and nothing else.
const POLL_MS = 2500
interface LiveState { lastSync: number | null; online: boolean }
let live: LiveState = { lastSync: null, online: true }
let stamp: string | null = null
const liveListeners = new Set<() => void>()
const setLive = (next: LiveState) => { live = next; liveListeners.forEach((l) => l()) }

export function useLive(): LiveState {
  const [s, set] = useState(live)
  useEffect(() => {
    const l = () => set(live)
    liveListeners.add(l)
    return () => { liveListeners.delete(l) }
  }, [])
  return s
}

export function startLiveSync(): () => void {
  let stopped = false
  let timer: number | undefined
  const tick = async () => {
    if (stopped) return
    if (!document.hidden) {
      try {
        const r = await api<{ stamp: string }>('/api/sync/state')
        if (stamp !== null && r.stamp !== stamp) refreshAll()
        stamp = r.stamp
        setLive({ lastSync: Date.now(), online: true })
      } catch {
        setLive({ ...live, online: false })
      }
    }
    if (!stopped) timer = window.setTimeout(tick, POLL_MS)
  }
  const onVisible = () => { if (!document.hidden) { window.clearTimeout(timer); void tick() } }
  document.addEventListener('visibilitychange', onVisible)
  void tick()
  return () => {
    stopped = true
    window.clearTimeout(timer)
    document.removeEventListener('visibilitychange', onVisible)
    stamp = null
  }
}

/** Upload a file as the raw request body (metadata goes in the query string). */
export function uploadFile<T>(path: string, file: File): Promise<T> {
  return api<T>(path, { method: 'POST', raw: file })
}

/** Download a stored document. The file is only reachable through this authenticated, ownership-checked call. */
export async function downloadDocument(id: number, filename: string): Promise<void> {
  const session = getSession()
  const res = await fetch(`/api/documents/${id}/download`, { cache: 'no-store', headers: session ? { Authorization: `Bearer ${session.token}` } : {} })
  if (!res.ok) {
    let msg = `Download failed (${res.status})`
    try { const j = await res.json(); if (typeof j.detail === 'string') msg = j.detail } catch { /* keep default */ }
    throw new ApiError(res.status, msg)
  }
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
