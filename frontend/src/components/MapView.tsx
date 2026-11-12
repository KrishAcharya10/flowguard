// Leaflet map with vector layers only (circleMarker / divIcon; never the default marker image).
// Works fully offline: the default background is a labelled grid. OSM tiles are optional and are
// removed automatically after three consecutive tile errors.
import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { fmtTime } from '../lib/format'

export interface MapRouteIn { id: string; name: string; alternative: boolean; points: { name: string; lat: number; lon: number; is_decision_node?: boolean }[] }
export interface MapVehicleIn { id: string; lat: number; lon: number; bucket?: string; reported_at?: string | null; age_min?: number | null; confidence?: string | null; label?: string }
export interface MapDisruptionIn { id: string; label: string; lat1: number; lon1: number; lat2: number; lon2: number }

const COLOR: Record<string, string> = { LATE: '#b91c1c', AT_RISK: '#b45309', ON_TRACK: '#15803d', ARRIVED_PENDING_POD: '#1d4ed8' }

export default function MapView({ routes, vehicles, disruptions = [], height = 420, onSelect, caption = 'Illustrative routes. Positions are simulated.' }: {
  routes: MapRouteIn[]; vehicles: MapVehicleIn[]; disruptions?: MapDisruptionIn[]; height?: number; onSelect?: (id: string) => void; caption?: string
}) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const tiles = useRef<L.TileLayer | null>(null)
  const fitted = useRef(false)
  const [useTiles, setUseTiles] = useState(false)
  const [tileNote, setTileNote] = useState('')

  useEffect(() => {
    if (!el.current || map.current) return
    const m = L.map(el.current, { zoomControl: true, attributionControl: false, preferCanvas: false }).setView([20, 75], 7)
    // labelled grid (the offline background)
    const grid = L.layerGroup().addTo(m)
    for (let lat = 10; lat <= 30; lat += 0.5) L.polyline([[lat, 65], [lat, 85]], { color: '#cbd5e1', weight: lat % 1 === 0 ? 1 : 0.5, interactive: false }).addTo(grid)
    for (let lon = 65; lon <= 85; lon += 0.5) L.polyline([[10, lon], [30, lon]], { color: '#cbd5e1', weight: lon % 1 === 0 ? 1 : 0.5, interactive: false }).addTo(grid)
    for (let lat = 10; lat <= 30; lat += 1) for (let lon = 65; lon <= 85; lon += 1) {
      L.marker([lat, lon], { interactive: false, icon: L.divIcon({ className: 'grid-label', html: `${String.fromCharCode(65 + (lon - 65))}${lat - 9}`, iconSize: [24, 12], iconAnchor: [-3, 14] }) }).addTo(grid)
    }
    layer.current = L.layerGroup().addTo(m)
    map.current = m
    return () => { m.remove(); map.current = null }
  }, [])

  useEffect(() => {
    const m = map.current
    if (!m) return
    if (useTiles && !tiles.current) {
      let errors = 0
      const t = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 12, opacity: 0.55 })
      t.on('tileload', () => { errors = 0 })
      t.on('tileerror', () => {
        errors += 1
        if (errors >= 3) {                      // offline or blocked: fall back to the labelled grid
          m.removeLayer(t)
          tiles.current = null
          setUseTiles(false)
          setTileNote('Map tiles unavailable (offline). Showing the labelled grid.')
        }
      })
      t.addTo(m)
      t.bringToBack()
      tiles.current = t
      setTileNote('')
    } else if (!useTiles && tiles.current) {
      m.removeLayer(tiles.current)
      tiles.current = null
    }
  }, [useTiles])

  useEffect(() => {
    const m = map.current
    const g = layer.current
    if (!m || !g) return
    g.clearLayers()
    const bounds: [number, number][] = []
    routes.forEach((r) => {
      const latlngs = r.points.map((p) => [p.lat, p.lon] as [number, number])
      bounds.push(...latlngs)
      L.polyline(latlngs, { color: r.alternative ? '#7c3aed' : '#12305a', weight: r.alternative ? 3 : 4, opacity: 0.8, dashArray: r.alternative ? '6 6' : undefined })
        .bindTooltip(`${r.name}${r.alternative ? ' (alternative route)' : ''}`, { sticky: true }).addTo(g)
      r.points.forEach((p, i) => {
        const end = i === 0 || i === r.points.length - 1
        L.circleMarker([p.lat, p.lon], { radius: p.is_decision_node ? 6 : end ? 5 : 3, color: '#12305a', weight: 2, fillColor: p.is_decision_node ? '#facc15' : '#fff', fillOpacity: 1 })
          .bindTooltip(`${p.name}${p.is_decision_node ? ' (decision node)' : ''}`).addTo(g)
        if (end && !r.alternative) L.marker([p.lat, p.lon], { interactive: false, icon: L.divIcon({ className: 'map-label', html: p.name, iconSize: [10, 10], iconAnchor: [-8, 6] }) }).addTo(g)
      })
    })
    disruptions.forEach((d) => {
      L.polyline([[d.lat1, d.lon1], [d.lat2, d.lon2]], { color: '#dc2626', weight: 8, opacity: 0.85, dashArray: '2 10' }).bindTooltip(d.label, { sticky: true }).addTo(g)
      L.marker([(d.lat1 + d.lat2) / 2, (d.lon1 + d.lon2) / 2], { interactive: false, icon: L.divIcon({ className: 'map-label', html: `<span style="color:#b91c1c">✕ ${d.label}</span>`, iconSize: [10, 10], iconAnchor: [-10, 6] }) }).addTo(g)
    })
    vehicles.forEach((v) => {
      const stale = v.confidence === 'STALE'
      const c = L.circleMarker([v.lat, v.lon], { radius: 9, color: stale ? '#64748b' : '#0b1f3a', weight: 2, dashArray: stale ? '3 3' : undefined, fillColor: COLOR[v.bucket ?? ''] ?? '#1d4ed8', fillOpacity: stale ? 0.45 : 0.95 })
      const age = v.age_min !== null && v.age_min !== undefined ? ` (${Math.round(v.age_min)} min ago)` : ''
      c.bindTooltip(`<strong>${v.id}</strong><br/>${(v.bucket ?? '').replace(/_/g, ' ').toLowerCase()}<br/>Last reported: ${v.reported_at ? fmtTime(v.reported_at) + age : 'not yet departed'}${stale ? '<br/>⚠ stale: last REPORTED position' : ''}`)
      if (onSelect) c.on('click', () => onSelect(v.id))
      c.addTo(g)
      L.marker([v.lat, v.lon], { interactive: false, icon: L.divIcon({ className: 'map-label', html: v.label ?? v.id.replace('SHP-', ''), iconSize: [10, 10], iconAnchor: [-11, 18] }) }).addTo(g)
      bounds.push([v.lat, v.lon])
    })
    if (!fitted.current && bounds.length) {
      m.fitBounds(L.latLngBounds(bounds).pad(0.12))
      fitted.current = true
    }
  }, [routes, vehicles, disruptions, onSelect])

  return (
    <div>
      <div ref={el} style={{ height }} className="rounded-md border border-slate-300 bg-slate-50 z-0" role="img" aria-label="Map of illustrative routes and last reported vehicle positions" />
      <div className="flex flex-wrap items-center justify-between gap-2 mt-1 text-xs text-slate-600">
        <span>{caption}</span>
        <span className="flex items-center gap-3">
          <span><span className="text-green-700">●</span> on track <span className="text-amber-700">●</span> at risk <span className="text-red-700">●</span> late <span className="text-blue-700">●</span> arrived <span className="text-violet-700">┅</span> alternative</span>
          <label className="flex items-center gap-1"><input type="checkbox" checked={useTiles} onChange={(e) => setUseTiles(e.target.checked)} /> Background tiles (needs internet)</label>
        </span>
      </div>
      {tileNote && <div className="text-xs text-amber-800 mt-1">{tileNote}</div>}
    </div>
  )
}
