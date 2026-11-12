// Operational map built on Leaflet (vector layers only, no marker images, no keys, no paid service).
//
// Two backgrounds, one set of overlays:
//   GEOGRAPHIC  OpenStreetMap tiles, on by default when the browser is online. Attribution is always shown.
//   OFFLINE     a locally drawn logistics network (no network needed). Used automatically when tiles cannot load,
//               and labelled "Illustrative logistics network - not to scale".
// Routes, decision nodes, disruptions and vehicles are identical in both modes.
//
// Performance rules: route / place / disruption layers are rebuilt only when their own data changes, vehicles are
// redrawn when positions change or the view moves (they are few), the view is fitted once per `fitKey` and never
// reset by a data refresh, and every layer, observer and listener is removed on unmount.
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fmtTime } from '../lib/format'

export interface MapPointIn { name: string; lat: number; lon: number; is_decision_node?: boolean }
export interface MapRouteIn { id: string; name: string; alternative: boolean; alternativeOf?: string | null; points: MapPointIn[] }
export interface MapVehicleIn {
  id: string; lat: number; lon: number; bucket?: string; reported_at?: string | null; age_min?: number | null
  confidence?: string | null; label?: string; onAlt?: boolean; routeId?: string; risk?: string | null
}
export interface MapDisruptionIn { id: string; label: string; lat1: number; lon1: number; lat2: number; lon2: number }
export interface MapViewHandle { zoomIn(): void; zoomOut(): void; fitAll(): void; centerPlant(): void; centerOn(id: string, rightPad?: number): void }
export type MapMode = 'auto' | 'geographic' | 'offline'

export const STATUS_COLOR: Record<string, string> = { LATE: '#dc2626', AT_RISK: '#d97706', ON_TRACK: '#16a34a', ARRIVED_PENDING_POD: '#2563eb', DELIVERED: '#64748b', SPLIT_PARENT: '#64748b' }
export const STATUS_LABEL: Record<string, string> = { LATE: 'Late', AT_RISK: 'At risk', ON_TRACK: 'On track', ARRIVED_PENDING_POD: 'Arrived, POD pending', DELIVERED: 'Delivered', SPLIT_PARENT: 'Split parent' }
const GLYPH: Record<string, string> = { LATE: '●', AT_RISK: '▲', ON_TRACK: '✓', ARRIVED_PENDING_POD: '◆' }
const RANK: Record<string, number> = { LATE: 0, AT_RISK: 1, ARRIVED_PENDING_POD: 2, ON_TRACK: 3 }
const STALE_GREY = '#64748b'
const ROUTE_NAVY = '#12305a'
const ALT_VIOLET = '#7c3aed'
const TILE_URL = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a> contributors'

const SVG = (d: string) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="${d}"/></svg>`
const TRUCK = SVG('M1 6h13v10H1zM14 10h5l3 3v3h-8zM6 19a2 2 0 100-4 2 2 0 000 4zM18 19a2 2 0 100-4 2 2 0 000 4z')
const FACTORY = SVG('M2 20V9l6 4V9l6 4V4h4v16zM6 20v-3M11 20v-3')
const FLAG = SVG('M4 22V4M4 4h13l-2 4 2 4H4')

const esc = (s: unknown) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c] as string)
const same = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) => Math.abs(a.lat - b.lat) < 1e-4 && Math.abs(a.lon - b.lon) < 1e-4
const key = (p: { lat: number; lon: number }) => `${p.lat.toFixed(3)},${p.lon.toFixed(3)}`
const statusColor = (v: MapVehicleIn) => (v.confidence === 'STALE' ? STALE_GREY : STATUS_COLOR[v.bucket ?? ''] ?? '#2563eb')
/** The point `f` (0..1) along a path, and whether the path is running mostly north-south there. */
function along(points: MapPointIn[], f: number): { lat: number; lon: number; vertical: boolean } | null {
  if (points.length < 2) return null
  const k = Math.cos((points[0].lat * Math.PI) / 180)
  const seg = points.slice(1).map((p, i) => { const a = points[i]; const dx = (p.lon - a.lon) * k; const dy = p.lat - a.lat; return { a, p, len: Math.hypot(dx, dy), vertical: Math.abs(dy) >= Math.abs(dx) } })
  const total = seg.reduce((s, x) => s + x.len, 0)
  let want = total * f
  for (const x of seg) {
    if (want <= x.len || x === seg[seg.length - 1]) { const t = x.len ? Math.min(1, want / x.len) : 0; return { lat: x.a.lat + (x.p.lat - x.a.lat) * t, lon: x.a.lon + (x.p.lon - x.a.lon) * t, vertical: x.vertical } }
    want -= x.len
  }
  return null
}
const coord = (lat: number, lon: number) => `${Math.abs(lat).toFixed(3)}°${lat >= 0 ? 'N' : 'S'} ${Math.abs(lon).toFixed(3)}°${lon >= 0 ? 'E' : 'W'}`

/** Locally drawn background (dot lattice on a soft blue-grey). No labels: it must not look like a coordinate grid. */
function offlineLayer(): L.GridLayer {
  const g = L.gridLayer({ tileSize: 256, className: 'fg-offline-tiles' }) as L.GridLayer & { createTile: (c: L.Coords) => HTMLElement }
  g.createTile = () => {
    const c = document.createElement('canvas')
    c.width = c.height = 256
    const x = c.getContext('2d')
    if (!x) return c
    x.fillStyle = '#e3eaf3'
    x.fillRect(0, 0, 256, 256)
    x.fillStyle = 'rgba(100, 125, 160, 0.20)'
    for (let i = 0; i < 256; i += 32) for (let j = 0; j < 256; j += 32) { x.beginPath(); x.arc(i + 16, j + 16, i % 128 === 112 && j % 128 === 112 ? 2.2 : 1.1, 0, Math.PI * 2); x.fill() }
    return c
  }
  return g
}

interface Props {
  routes: MapRouteIn[]
  vehicles: MapVehicleIn[]
  disruptions?: MapDisruptionIn[]
  height?: number | string
  onSelect?: (id: string) => void
  selectedId?: string | null
  highlightRouteIds?: string[]
  showAlt?: boolean
  showDisruptions?: boolean
  mode?: MapMode
  fitKey?: string
  zoomControl?: boolean
  caption?: string
}

const MapView = forwardRef<MapViewHandle, Props>(function MapView({
  routes, vehicles, disruptions = [], height = 420, onSelect, selectedId = null, highlightRouteIds = [], showAlt = true,
  showDisruptions = true, mode = 'auto', fitKey = 'default', zoomControl = false, caption = 'Illustrative routes. Positions are simulated.',
}, ref) {
  const el = useRef<HTMLDivElement>(null)
  const root = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const groups = useRef<{ routes: L.LayerGroup; places: L.LayerGroup; dis: L.LayerGroup; veh: L.LayerGroup } | null>(null)
  const base = useRef<L.Layer | null>(null)
  const fitted = useRef<string | null>(null)
  const fan = useRef<string | null>(null)
  const latest = useRef({ vehicles, selectedId, onSelect, routes, disruptions })
  latest.current = { vehicles, selectedId, onSelect, routes, disruptions }

  const [pref, setPref] = useState<MapMode>(mode)
  const [effective, setEffective] = useState<'geographic' | 'offline'>(() => (mode === 'offline' || (typeof navigator !== 'undefined' && navigator.onLine === false) ? 'offline' : 'geographic'))
  const [tile, setTile] = useState<'idle' | 'loading' | 'ready' | 'partial'>('idle')
  const [note, setNote] = useState('')
  const [retryN, setRetryN] = useState(0)
  useEffect(() => { setPref(mode); if (mode === 'offline') setEffective('offline'); if (mode === 'geographic') setEffective('geographic') }, [mode])

  // ---------------------------------------------------------------- derived, stable signatures
  const plant = useMemo(() => routes.find((r) => !r.alternative)?.points[0] ?? null, [routes])
  const activeAlt = useMemo(() => {
    const ids = new Set<string>()
    vehicles.filter((v) => v.onAlt).forEach((v) => routes.forEach((r) => { if (r.alternative && (r.id === v.routeId || r.alternativeOf === v.routeId)) ids.add(r.id) }))
    return ids
  }, [vehicles, routes])
  const routeSig = JSON.stringify([routes.map((r) => [r.id, r.alternative, r.points.length, r.points[0]?.lat, r.points[r.points.length - 1]?.lat]), showAlt, [...activeAlt].sort(), highlightRouteIds])
  const disSig = JSON.stringify([disruptions.map((d) => [d.id, d.lat1, d.lon1, d.lat2, d.lon2]), showDisruptions])
  const vehSig = JSON.stringify([vehicles.map((v) => [v.id, v.lat, v.lon, v.bucket, v.confidence, v.onAlt, v.age_min == null ? null : Math.round(v.age_min)]), selectedId])

  // ---------------------------------------------------------------- vehicles (decluttered)
  const renderVehicles = useCallback(() => {
    const m = map.current
    const g = groups.current?.veh
    if (!m || !g) return
    g.clearLayers()
    const { vehicles: vs, selectedId: sel } = latest.current
    const plantPt = plant ? m.latLngToContainerPoint([plant.lat, plant.lon]) : null
    const items = vs.map((v) => {
      let p = m.latLngToContainerPoint([v.lat, v.lon])
      if (plantPt && Math.hypot(p.x - plantPt.x, p.y - plantPt.y) < 30) p = L.point(p.x + 30, p.y - 36)   // keep the plant icon visible
      return { v, p }
    }).sort((a, b) => (RANK[a.v.bucket ?? ''] ?? 4) - (RANK[b.v.bucket ?? ''] ?? 4))

    const clusters: { items: typeof items; cx: number; cy: number }[] = []
    for (const it of items) {
      const hit = it.v.id === sel ? undefined : clusters.find((c) => !c.items.some((x) => x.v.id === sel) && Math.hypot(c.cx - it.p.x, c.cy - it.p.y) < 40)
      if (hit) { hit.items.push(it); hit.cx = hit.items.reduce((s, x) => s + x.p.x, 0) / hit.items.length; hit.cy = hit.items.reduce((s, x) => s + x.p.y, 0) / hit.items.length } else clusters.push({ items: [it], cx: it.p.x, cy: it.p.y })
    }

    const taken: { x: number; y: number; w: number; h: number }[] = []
    const overlaps = (r: { x: number; y: number; w: number; h: number }) => taken.some((t) => r.x < t.x + t.w && r.x + r.w > t.x && r.y < t.y + t.h && r.y + r.h > t.y)
    const place = (v: MapVehicleIn, p: L.Point) => {
      const lbl = v.label ?? v.id.replace('SHP-', '')
      const w = lbl.length * 6.4 + 22
      const rect = { x: p.x - w / 2, y: p.y + 20, w, h: 18 }
      const hide = v.id !== sel && overlaps(rect)
      taken.push({ x: p.x - 18, y: p.y - 18, w: 36, h: 36 }, ...(hide ? [] : [rect]))
      const col = statusColor(v)
      const fresh = v.confidence === 'STALE' ? 'stale' : v.confidence === 'AGING' ? 'aging' : 'fresh'
      const age = v.age_min == null ? '' : ` (${Math.round(v.age_min)} min ago)`
      const html = `<div class="fg-veh${v.confidence === 'STALE' ? ' fg-stale' : ''}${v.id === sel ? ' fg-sel' : ''}" style="--c:${col}"><div class="fg-pin">${TRUCK}<i class="fg-fresh ${fresh}"></i></div><div class="fg-tag${hide ? ' fg-hide' : ''}">${esc(lbl)} ${GLYPH[v.bucket ?? ''] ?? ''}</div></div>`
      const mk = L.marker(m.containerPointToLatLng(p), { icon: L.divIcon({ className: '', html, iconSize: [34, 34], iconAnchor: [17, 17] }), keyboard: true, riseOnHover: true, alt: `Shipment ${v.id}, ${STATUS_LABEL[v.bucket ?? ''] ?? ''}` })
      mk.bindTooltip(`<strong>${esc(v.id)}</strong><br/>${esc(STATUS_LABEL[v.bucket ?? ''] ?? '')}${v.risk ? ` · risk ${esc(v.risk.toLowerCase())}` : ''}<br/>Last reported: ${v.reported_at ? `${esc(fmtTime(v.reported_at))}${age}<br/>${coord(v.lat, v.lon)}` : 'not departed yet'}${v.confidence === 'STALE' ? '<br/><b>⚠ stale: last REPORTED position</b>' : v.confidence === 'AGING' ? '<br/>data ageing' : ''}`, { direction: 'top', offset: [0, -20] })
      mk.on('click', () => latest.current.onSelect?.(v.id))
      mk.addTo(g)
    }

    for (const c of clusters) {
      if (c.items.length === 1) { place(c.items[0].v, c.items[0].p); continue }
      const ck = c.items.map((x) => x.v.id).sort().join('|')
      const worst = c.items[0].v
      if (fan.current === ck) {                                    // fanned out: members around the centre
        const centre = L.point(c.cx, c.cy)
        const r = 36 + c.items.length * 5
        c.items.forEach((it, i) => {
          const a = (-Math.PI / 2) + (i * 2 * Math.PI) / c.items.length
          const p = L.point(c.cx + r * Math.cos(a), c.cy + r * Math.sin(a))
          L.polyline([m.containerPointToLatLng(centre), m.containerPointToLatLng(p)], { color: '#475569', weight: 1.5, interactive: false }).addTo(g)
          place(it.v, p)
        })
        L.marker(m.containerPointToLatLng(centre), { icon: L.divIcon({ className: '', html: `<div class="fg-cluster" style="--c:${STATUS_COLOR[worst.bucket ?? ''] ?? '#1d4ed8'};width:26px;height:26px;font-size:11px">${c.items.length}</div>`, iconSize: [26, 26], iconAnchor: [13, 13] }), keyboard: false }).on('click', () => { fan.current = null; renderVehicles() }).addTo(g)
        taken.push({ x: c.cx - 14, y: c.cy - 14, w: 28, h: 28 })
        continue
      }
      taken.push({ x: c.cx - 22, y: c.cy - 22, w: 44, h: 60 })
      const names = c.items.map((x) => x.v.id.replace('SHP-', '')).join(', ')
      const mk = L.marker(m.containerPointToLatLng(L.point(c.cx, c.cy)), { icon: L.divIcon({ className: '', html: `<div class="fg-cluster" style="--c:${STATUS_COLOR[worst.bucket ?? ''] ?? '#1d4ed8'}">${c.items.length}<small></div>`, iconSize: [42, 42], iconAnchor: [21, 21] }), keyboard: true, alt: `${c.items.length} shipments grouped: ${names}` })
      mk.bindTooltip(`<strong>${c.items.length} shipments</strong><br/>${esc(names)}<br/><i>Click to expand</i>`, { direction: 'top', offset: [0, -22] })
      mk.on('click', () => {
        const b = L.latLngBounds(c.items.map((x) => [x.v.lat, x.v.lon] as [number, number]))
        const span = Math.max(b.getNorth() - b.getSouth(), b.getEast() - b.getWest())
        if (span < 0.003 || m.getZoom() >= 13) { fan.current = ck; renderVehicles() } else m.flyToBounds(b.pad(0.5), { maxZoom: 12, duration: 0.5 })
      })
      mk.addTo(g)
    }
  }, [plant])

  // ---------------------------------------------------------------- map creation
  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: false, attributionControl: false, preferCanvas: false, zoomSnap: 0.5, minZoom: 4, maxZoom: 18 }).setView([20, 75.5], 7)
    L.control.attribution({ prefix: false, position: 'bottomright' }).addTo(m)
    if (zoomControl) L.control.zoom({ position: 'topleft' }).addTo(m)
    groups.current = { routes: L.layerGroup().addTo(m), places: L.layerGroup().addTo(m), dis: L.layerGroup().addTo(m), veh: L.layerGroup().addTo(m) }
    map.current = m
    const lo = () => root.current?.classList.toggle('fg-zoom-lo', m.getZoom() < 8)
    const redraw = () => renderVehicles()
    m.on('zoomstart', () => { fan.current = null })
    m.on('zoomend', () => { lo(); redraw() })
    m.on('moveend', redraw)
    m.on('click', () => { if (fan.current) { fan.current = null; redraw() } })
    lo()
    const ro = new ResizeObserver(() => m.invalidateSize({ animate: false }))     // resize, fullscreen, tab shown
    if (root.current) ro.observe(root.current)
    const io = new IntersectionObserver((e) => { if (e.some((x) => x.isIntersecting)) m.invalidateSize({ animate: false }) })
    if (root.current) io.observe(root.current)
    return () => { ro.disconnect(); io.disconnect(); m.remove(); map.current = null; groups.current = null; base.current = null }
  }, [renderVehicles, zoomControl])

  // ---------------------------------------------------------------- background: tiles or the local network
  useEffect(() => {
    const m = map.current
    if (!m) return
    if (base.current) { m.removeLayer(base.current); base.current = null }
    root.current?.classList.toggle('fg-offline', effective === 'offline')
    if (effective === 'offline') {
      const l = offlineLayer().addTo(m)
      base.current = l
      setTile('idle')
      return
    }
    let loaded = 0, errors = 0, total = 0
    const t = L.tileLayer(TILE_URL, { maxZoom: 18, attribution: ATTRIBUTION, crossOrigin: false })
    const giveUp = (why: string) => { setNote(why); setEffective('offline') }
    const timer = window.setTimeout(() => { if (loaded === 0) giveUp('Map tiles did not load (no internet). Showing the offline logistics network.') }, 9000)
    t.on('loading', () => setTile('loading'))
    t.on('tileload', () => { loaded += 1; errors = 0; setNote('') })
    t.on('tileerror', () => {
      errors += 1; total += 1
      if (loaded === 0 && errors >= 3) giveUp('Map tiles are unavailable. Showing the offline logistics network.')
      else if (errors >= 3) setTile('partial')
    })
    t.on('load', () => setTile(total > 0 && loaded === 0 ? 'partial' : total > 0 ? 'partial' : 'ready'))
    t.addTo(m)
    base.current = t
    setNote('')
    return () => { window.clearTimeout(timer); t.off() }
  }, [effective, retryN])

  // come back online -> try the real map again (only when the user has not pinned the offline map)
  useEffect(() => {
    const on = () => { if (pref !== 'offline') { setEffective('geographic'); setRetryN((n) => n + 1) } }
    window.addEventListener('online', on)
    return () => window.removeEventListener('online', on)
  }, [pref])

  // ---------------------------------------------------------------- routes, places (rebuilt only when they change)
  useEffect(() => {
    const m = map.current
    const g = groups.current
    if (!m || !g) return
    g.routes.clearLayers()
    g.places.clearLayers()
    const highlight = new Set(highlightRouteIds)
    const placed = new Set<string>()
    const label = (lat: number, lon: number, html: string, cls: string, anchor: [number, number] = [-6, 4]) =>
      L.marker([lat, lon], { interactive: false, keyboard: false, icon: L.divIcon({ className: '', html: `<span class="${cls}">${html}</span>`, iconSize: [1, 1], iconAnchor: anchor }) }).addTo(g.places)

    const primaries = routes.filter((r) => !r.alternative)
    const alts = routes.filter((r) => r.alternative && showAlt)

    // soft corridor + casing + line
    const draw = (r: MapRouteIn, opts: { color: string; weight: number; dash?: string; opacity?: number; glow?: boolean }) => {
      const ll = r.points.map((p) => [p.lat, p.lon] as [number, number])
      if (opts.glow) L.polyline(ll, { color: opts.color, weight: opts.weight + 12, opacity: 0.16, interactive: false }).addTo(g.routes)
      L.polyline(ll, { color: '#ffffff', weight: opts.weight + 4, opacity: 0.95, interactive: false, lineCap: 'round' }).addTo(g.routes)
      return L.polyline(ll, { color: opts.color, weight: opts.weight, opacity: opts.opacity ?? 1, dashArray: opts.dash, lineCap: 'round' }).addTo(g.routes)
    }
    primaries.forEach((r) => {
      const hl = highlight.has(r.id)
      draw(r, { color: ROUTE_NAVY, weight: hl ? 6 : 4.5, glow: hl }).bindTooltip(`<strong>${esc(r.name)}</strong><br/>Primary route`, { sticky: true })
    })
    // a rerouted truck: bypassed section dimmed, the bypass drawn solid and labelled
    alts.forEach((r) => {
      const active = activeAlt.has(r.id)
      const parent = primaries.find((p) => p.id === r.alternativeOf)
      if (active && parent) {
        const a = parent.points.findIndex((p) => same(p, r.points[0]))
        const b = parent.points.findIndex((p) => same(p, r.points[r.points.length - 1]))
        if (a >= 0 && b > a) L.polyline(parent.points.slice(a, b + 1).map((p) => [p.lat, p.lon] as [number, number]), { color: '#94a3b8', weight: 5, dashArray: '2 9', opacity: 1, interactive: false }).bindTooltip('Bypassed section', { sticky: true }).addTo(g.routes)
      }
      const line = active ? draw(r, { color: ALT_VIOLET, weight: 6, glow: true }) : draw(r, { color: ALT_VIOLET, weight: highlight.has(r.id) ? 5 : 4, dash: '9 9', opacity: 0.95 })
      line.bindTooltip(`<strong>${esc(r.name)}</strong><br/>${active ? 'ACTIVE REROUTE: operational route' : 'Alternative route (not in use)'}`, { sticky: true })
    })

    // places
    primaries.forEach((r) => {
      r.points.forEach((p, i) => {
        const k = key(p)
        if (placed.has(k)) return
        placed.add(k)
        if (i === 0) {
          L.marker([p.lat, p.lon], { keyboard: false, zIndexOffset: -50, icon: L.divIcon({ className: '', html: `<div class="fg-plant" title="Plant X">${FACTORY}</div>`, iconSize: [34, 34], iconAnchor: [17, 17] }) }).bindTooltip('<strong>Plant X</strong><br/>Waluj MIDC. All routes start here.', { direction: 'left' }).addTo(g.places)
          label(p.lat, p.lon, 'Plant X', 'fg-place fg-left', [0, 0])
        } else if (i === r.points.length - 1) {
          L.marker([p.lat, p.lon], { keyboard: false, zIndexOffset: -40, icon: L.divIcon({ className: '', html: `<span class="fg-dest"><i>${FLAG}</i>${esc(p.name)}</span>`, iconSize: [1, 1], iconAnchor: [10, 10] }) }).bindTooltip(`<strong>${esc(p.name)}</strong><br/>Delivery destination`, { direction: 'right' }).addTo(g.places)
        } else if (p.is_decision_node) {
          L.marker([p.lat, p.lon], { keyboard: false, zIndexOffset: -30, icon: L.divIcon({ className: '', html: '<div class="fg-node"></div>', iconSize: [14, 14], iconAnchor: [7, 7] }) }).bindTooltip(`<strong>${esc(p.name)}</strong><br/>Decision node: where a reroute can start`, { direction: 'right' }).addTo(g.places)
          label(p.lat, p.lon, esc(p.name), 'fg-place fg-wp-label', [-12, 6])
        } else {
          L.marker([p.lat, p.lon], { keyboard: false, zIndexOffset: -60, icon: L.divIcon({ className: '', html: '<div class="fg-wp"></div>', iconSize: [8, 8], iconAnchor: [4, 4] }) }).bindTooltip(esc(p.name), { direction: 'right' }).addTo(g.places)
          label(p.lat, p.lon, esc(p.name), 'fg-place fg-wp-label', [-9, 5])
        }
      })
    })
    alts.forEach((r) => r.points.forEach((p, i) => {
      const k = key(p)
      if (placed.has(k) || i === 0 || i === r.points.length - 1) return
      placed.add(k)
      L.circleMarker([p.lat, p.lon], { radius: 4, color: ALT_VIOLET, weight: 2, fillColor: '#fff', fillOpacity: 1 }).bindTooltip(`${esc(p.name)} (alternative route)`).addTo(g.places)
      label(p.lat, p.lon, esc(p.name), 'fg-place fg-wp-label', [-9, 5])
    }))
    // route name labels: 55% along the line, set beside it (not on top of it or of the places)
    routes.forEach((r) => {
      if (r.alternative && !showAlt) return
      const at = along(r.points, r.alternative ? 0.5 : 0.55)
      if (!at) return
      const active = activeAlt.has(r.id)
      label(at.lat, at.lon, active ? `↪ ${esc(r.name)} · active reroute` : r.alternative ? `${esc(r.name)} (alt)` : esc(r.name), `fg-routelabel ${at.vertical ? 'v' : 'h'}${r.alternative ? ' alt' : ''}${active ? ' active' : ''}`, [0, 0])
    })
  }, [routeSig])    // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------- disruption overlays
  useEffect(() => {
    const g = groups.current?.dis
    if (!g) return
    g.clearLayers()
    if (!showDisruptions) return
    disruptions.forEach((d) => {
      const ll: [number, number][] = [[d.lat1, d.lon1], [d.lat2, d.lon2]]
      L.polyline(ll, { color: '#dc2626', weight: 22, opacity: 0.22, interactive: false, lineCap: 'round' }).addTo(g)
      L.polyline(ll, { color: '#dc2626', weight: 6, opacity: 0.95, dashArray: '3 9', lineCap: 'round' }).bindTooltip(`<strong>${esc(d.label)}</strong><br/>Active disruption · road affected`, { sticky: true }).addTo(g)
      const mid: [number, number] = [(d.lat1 + d.lat2) / 2, (d.lon1 + d.lon2) / 2]
      L.marker(mid, { interactive: false, keyboard: false, icon: L.divIcon({ className: '', html: '<div class="fg-pulse"></div>', iconSize: [22, 22], iconAnchor: [11, 11] }) }).addTo(g)
      L.marker(mid, { interactive: false, keyboard: false, icon: L.divIcon({ className: '', html: `<span class="fg-dis">✕ ${esc(d.label)}</span>`, iconSize: [1, 1], iconAnchor: [0, 0] }) }).addTo(g)
    })
  }, [disSig])    // eslint-disable-line react-hooks/exhaustive-deps

  // ---------------------------------------------------------------- vehicles
  useEffect(() => { renderVehicles() }, [vehSig, renderVehicles])

  // ---------------------------------------------------------------- fit once per fitKey, never on a plain data refresh
  const fitAll = useCallback((animate = true) => {
    const m = map.current
    if (!m) return
    const { routes: rs, vehicles: vs, disruptions: ds } = latest.current
    const pts: [number, number][] = [...rs.flatMap((r) => r.points.map((p) => [p.lat, p.lon] as [number, number])), ...vs.map((v) => [v.lat, v.lon] as [number, number]), ...ds.flatMap((d) => [[d.lat1, d.lon1], [d.lat2, d.lon2]] as [number, number][])]
    if (!pts.length) return false
    m.fitBounds(L.latLngBounds(pts).pad(0.04), { padding: [20, 20], animate })
    return true
  }, [])
  useEffect(() => {
    if (fitted.current === fitKey || routes.length === 0) return
    if (fitAll(false)) fitted.current = fitKey
  }, [fitKey, routes.length, fitAll])

  useImperativeHandle(ref, () => ({
    zoomIn: () => map.current?.zoomIn(),
    zoomOut: () => map.current?.zoomOut(),
    fitAll: () => { fitAll(true) },
    centerPlant: () => { if (plant) map.current?.flyTo([plant.lat, plant.lon], Math.max(map.current.getZoom(), 9), { duration: 0.6 }) },
    centerOn: (id: string, rightPad = 0) => {           // rightPad keeps the truck clear of a panel on the right
      const v = latest.current.vehicles.find((x) => x.id === id)
      const m = map.current
      if (v && m) m.flyToBounds(L.latLngBounds([[v.lat, v.lon], [v.lat, v.lon]]), { maxZoom: Math.max(m.getZoom(), 9), paddingBottomRight: [rightPad, 0], duration: 0.6 })
    },
  }), [fitAll, plant])

  const choose = (p: MapMode) => { setPref(p); setNote(''); if (p === 'offline') setEffective('offline'); else { setEffective('geographic'); setRetryN((n) => n + 1) } }

  return (
    <div ref={root} className="fg-map overflow-hidden" style={{ height, isolation: 'isolate' }}>
      <div ref={el} className="absolute inset-0" role="application" aria-label="Operational map of Plant X routes and the last reported vehicle positions" />

      <div className="absolute left-3 bottom-3 z-[800] flex flex-col items-start gap-1.5 pointer-events-none">
        {effective === 'offline' && <div className="fg-chip !bg-navy-900 !text-white !border-navy-900 pointer-events-auto" data-testid="map-offline-label">Illustrative logistics network — not to scale</div>}
        {effective === 'geographic' && tile === 'loading' && <div className="fg-chip pointer-events-auto" role="status" data-testid="map-loading">Loading map tiles…</div>}
        {effective === 'geographic' && tile === 'partial' && <div className="fg-chip !text-amber-800 !border-amber-300 pointer-events-auto" role="status">Some map tiles did not load</div>}
        {note && <div className="fg-chip !text-amber-900 !border-amber-300 !bg-amber-50 pointer-events-auto max-w-xs" role="status" data-testid="map-note">{note}
          <button className="ml-2 underline font-semibold" onClick={() => choose('geographic')}>Retry online map</button></div>}
        <div className="pointer-events-auto inline-flex rounded-md overflow-hidden border border-slate-300 bg-white shadow-card" role="group" aria-label="Map background">
          <button className={`px-2.5 py-1 text-[11px] font-semibold ${effective === 'geographic' ? 'bg-navy-900 text-white' : 'text-slate-700 hover:bg-slate-50'}`} aria-pressed={effective === 'geographic'} onClick={() => choose('geographic')}>Map</button>
          <button className={`px-2.5 py-1 text-[11px] font-semibold border-l border-slate-300 ${effective === 'offline' ? 'bg-navy-900 text-white' : 'text-slate-700 hover:bg-slate-50'}`} aria-pressed={effective === 'offline'} onClick={() => choose('offline')}>Network</button>
        </div>
      </div>
      {effective === 'geographic' && <div className="sr-only">{caption}</div>}
    </div>
  )
})

export default MapView
