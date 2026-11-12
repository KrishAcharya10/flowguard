// The Control Tower's main work surface: the live map plus its tools (zoom, fit, centre, full screen, layer toggles,
// status / risk / transporter filters, shipment search), a legend and a vehicle detail panel. All data is the real
// control-tower data passed in by the page; nothing is mocked here.
import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ControlTower as CT, MapData } from '../api/client'
import { fmtEta, fmtTime, pct } from '../lib/format'
import Icon from './Icons'
import MapView, { STATUS_COLOR, STATUS_LABEL, type MapViewHandle } from './MapView'
import { BucketBadge, ConfidenceBadge, RiskBadge } from './ui'

type Ship = CT['shipments'][number]
const STATUSES = ['LATE', 'AT_RISK', 'ON_TRACK', 'ARRIVED_PENDING_POD'] as const

function Swatch({ children, label }: { children: React.ReactNode; label: string }) {
  return <li className="flex items-center gap-2"><span className="w-7 flex justify-center shrink-0">{children}</span><span>{label}</span></li>
}

function Legend({ onClose }: { onClose: () => void }) {
  const dot = (c: string, dashed = false) => <span className="h-3.5 w-3.5 rounded-full border-2" style={{ background: dashed ? '#fff' : c, borderColor: dashed ? '#94a3b8' : '#fff', boxShadow: '0 0 0 1px rgba(15,23,42,.4)', borderStyle: dashed ? 'dashed' : 'solid' }} />
  return (
    <div className="w-64 rounded-lg border border-slate-300 bg-white/97 shadow-pop p-3 text-[12px] text-slate-700" role="dialog" aria-label="Map legend" data-testid="map-legend">
      <div className="flex items-center justify-between mb-1.5"><span className="font-bold text-navy-900">Legend</span><button className="fg-ctl !h-6 !w-6" aria-label="Close legend" onClick={onClose}><Icon name="x" size={13} /></button></div>
      <div className="label !text-[10px] mb-1">Vehicles (status)</div>
      <ul className="space-y-1">
        <Swatch label="On track ✓">{dot(STATUS_COLOR.ON_TRACK)}</Swatch>
        <Swatch label="At risk ▲">{dot(STATUS_COLOR.AT_RISK)}</Swatch>
        <Swatch label="Late ●">{dot(STATUS_COLOR.LATE)}</Swatch>
        <Swatch label="Arrived, POD pending ◆">{dot(STATUS_COLOR.ARRIVED_PENDING_POD)}</Swatch>
        <Swatch label="Stale position (grey, dashed ring)">{dot('#64748b', true)}</Swatch>
      </ul>
      <div className="label !text-[10px] mt-2 mb-1">Data freshness (dot on the truck)</div>
      <ul className="space-y-1">
        <Swatch label="Fresh report"><span className="h-2.5 w-2.5 rounded-full bg-green-600" /></Swatch>
        <Swatch label="Ageing"><span className="h-2.5 w-2.5 rounded-full bg-slate-400" /></Swatch>
        <Swatch label="Stale (last REPORTED position)"><span className="h-2.5 w-2.5 rounded-full bg-amber-500" /></Swatch>
      </ul>
      <div className="label !text-[10px] mt-2 mb-1">Routes and places</div>
      <ul className="space-y-1">
        <Swatch label="Primary route"><span className="block w-7 h-1 rounded bg-navy-800" /></Swatch>
        <Swatch label="Alternative route (not in use)"><span className="block w-7 border-t-[3px] border-dashed border-violet-600" /></Swatch>
        <Swatch label="Active reroute (approved)"><span className="block w-7 h-1.5 rounded bg-violet-600" /></Swatch>
        <Swatch label="Road disruption"><span className="block w-7 border-t-[4px] border-dotted border-red-600" /></Swatch>
        <Swatch label="Plant X"><span className="h-4 w-4 rounded bg-navy-900 text-white flex items-center justify-center"><Icon name="factory" size={10} /></span></Swatch>
        <Swatch label="Customer destination"><span className="h-3.5 w-3.5 rounded-full bg-navy-900 text-white flex items-center justify-center"><Icon name="flag" size={8} /></span></Swatch>
        <Swatch label="Decision node (reroute can start)"><span className="h-3 w-3 rotate-45 bg-yellow-400 border-2 border-navy-900" /></Swatch>
      </ul>
      <p className="text-[11px] text-slate-500 mt-2">Numbered discs group several trucks. Click one to zoom in or fan them out.</p>
    </div>
  )
}

function Detail({ ship, vehicle, onClose, onCentre }: { ship: Ship; vehicle?: MapData['vehicles'][number]; onClose: () => void; onCentre: () => void }) {
  const nav = useNavigate()
  const p = ship.prediction
  const row = (k: string, v: React.ReactNode) => <><dt className="text-slate-500">{k}</dt><dd className="font-medium text-slate-800 min-w-0">{v}</dd></>
  return (
    <aside className="w-[21rem] max-w-[calc(100vw-2rem)] max-h-full overflow-y-auto rounded-lg border border-slate-300 bg-white shadow-pop" aria-label={`Shipment ${ship.id} details`} data-testid="vehicle-panel">
      <div className="flex items-start gap-2 p-3 border-b border-slate-200 bg-slate-50 rounded-t-lg">
        <span className="h-9 w-9 rounded-full flex items-center justify-center text-white shrink-0" style={{ background: vehicle?.data_confidence === 'STALE' ? '#64748b' : STATUS_COLOR[ship.bucket] ?? '#2563eb' }}><Icon name="truck" size={18} /></span>
        <div className="min-w-0">
          <div className="font-bold text-navy-900 leading-tight break-all">{ship.id}</div>
          <div className="text-xs text-slate-500">{ship.order_id}{ship.priority === 'HIGH' ? ' · PRIORITY' : ''}</div>
        </div>
        <button className="fg-ctl !h-7 !w-7 ml-auto shrink-0" aria-label="Close shipment details" onClick={onClose}><Icon name="x" size={14} /></button>
      </div>
      <div className="p-3 space-y-3">
        <div className="flex flex-wrap gap-1.5"><BucketBadge bucket={ship.bucket} />{p && <RiskBadge level={p.risk_category} />}{p && p.data_confidence !== 'FRESH' && <ConfidenceBadge value={p.data_confidence} />}</div>
        <dl className="grid grid-cols-[6.5rem_1fr] gap-x-2 gap-y-1.5 text-[12.5px]">
          {row('Customer', ship.customer_name.replace(' (fictional)', ''))}
          {row('Driver', ship.driver_name?.replace(' (fictional)', '') ?? 'Not assigned')}
          {row('Transporter', ship.transporter_name.replace(' (fictional)', ''))}
          {row('Milestone', ship.state_label)}
          {row('Route', <>{ship.route_name}{ship.alternative_route_name && <span className="block text-violet-700">rerouted via {ship.alternative_route_name}</span>}</>)}
          {row('Original promise', fmtTime(ship.promised_at))}
          {row('Predicted ETA', p ? <>{fmtEta(p.p50_at)} <span className="text-slate-500 font-normal">(P50)</span></> : ship.arrived_at ? `arrived ${fmtTime(ship.arrived_at)}` : '-')}
          {row('P(late)', p ? <strong className={p.p_late >= 0.5 ? 'text-red-700' : ''}>{pct(p.p_late)}</strong> : '-')}
          {row('Last reported', vehicle?.reported_at ? <>{fmtTime(vehicle.reported_at)}{vehicle.age_min != null && <span className="text-slate-500 font-normal"> ({Math.round(vehicle.age_min)} min ago)</span>}<span className="block text-[11px] text-slate-500">{vehicle.lat.toFixed(3)}°N {vehicle.lon.toFixed(3)}°E</span></> : 'not departed yet')}
        </dl>
        <div className="flex flex-wrap gap-2 pt-1">
          <button className="btn-primary btn-sm" onClick={() => nav(`/shipments/${ship.id}`)}>Open shipment<Icon name="arrow" size={13} /></button>
          {p && ship.disposition === 'ACTIVE' && <button className="btn-accent btn-sm" onClick={() => nav(`/shipments/${ship.id}/war-room`)}>Open War Room</button>}
          <button className="btn-secondary btn-sm" onClick={onCentre}><Icon name="target" size={13} />Centre</button>
        </div>
      </div>
    </aside>
  )
}

export default function FleetMap({ data, shipments, selected, onSelect, height = 640 }: {
  data: MapData; shipments: Ship[]; selected: string | null; onSelect: (id: string | null) => void; height?: number | string
}) {
  const ref = useRef<MapViewHandle>(null)
  const box = useRef<HTMLDivElement>(null)
  const [full, setFull] = useState(false)
  const [legend, setLegend] = useState(false)
  const [showAlt, setShowAlt] = useState(true)
  const [showDis, setShowDis] = useState(true)
  const [status, setStatus] = useState<string>('')
  const [risk, setRisk] = useState('')
  const [trans, setTrans] = useState('')
  const [q, setQ] = useState('')

  const byId = useMemo(() => new Map(shipments.map((s) => [s.id, s])), [shipments])
  const transporters = useMemo(() => [...new Map(shipments.map((s) => [s.transporter_id, s.transporter_name.replace(' (fictional)', '')])).entries()], [shipments])
  const counts = useMemo(() => Object.fromEntries(STATUSES.map((k) => [k, data.vehicles.filter((v) => v.bucket === k).length])), [data.vehicles])
  const routes = useMemo(() => data.routes.map((r) => ({ id: r.id, name: r.name, alternative: !!r.alternative_of, alternativeOf: r.alternative_of, points: r.points })), [data.routes])
  const needle = q.trim().toLowerCase()
  const vehicles = useMemo(() => data.vehicles.filter((v) => {
    const s = byId.get(v.shipment_id)
    return (!status || v.bucket === status) && (!risk || v.risk_category === risk) && (!trans || s?.transporter_id === trans) &&
      (!needle || v.shipment_id.toLowerCase().includes(needle) || (s?.order_id ?? '').toLowerCase().includes(needle) || (s?.customer_name ?? '').toLowerCase().includes(needle))
  }).map((v) => ({ id: v.shipment_id, lat: v.lat, lon: v.lon, bucket: v.bucket, reported_at: v.reported_at, age_min: v.age_min, confidence: v.data_confidence, onAlt: v.on_alternative, routeId: v.route_id, risk: v.risk_category })), [data.vehicles, byId, status, risk, trans, needle])
  const selVehicle = data.vehicles.find((v) => v.shipment_id === selected)
  const selShip = selected ? byId.get(selected) : undefined
  const highlight = useMemo(() => {
    if (!selVehicle) return []
    return data.routes.filter((r) => r.id === selVehicle.route_id || r.alternative_of === selVehicle.route_id).map((r) => r.id)
  }, [data.routes, selVehicle])
  const fitKey = 'network'

  useEffect(() => { if (selected) ref.current?.centerOn(selected, 340) }, [selected])
  useEffect(() => {                                                // Esc leaves full screen; body does not scroll behind it
    if (!full) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setFull(false) }
    window.addEventListener('keydown', onKey)
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { window.removeEventListener('keydown', onKey); document.body.style.overflow = prev }
  }, [full])

  const chip = (k: string, label: string, n?: number) => (
    <button key={k} aria-pressed={status === k} onClick={() => setStatus(status === k ? '' : k)}
      className={`chip cursor-pointer ${status === k ? 'bg-navy-900 text-white border-navy-900' : 'bg-white text-slate-700 border-slate-300 hover:bg-slate-50'}`}>
      {k && <span className="h-2 w-2 rounded-full" style={{ background: STATUS_COLOR[k] }} />}{label}{n !== undefined && <span className="opacity-70">{n}</span>}
    </button>
  )
  return (
    <div ref={box} className={full ? 'fixed inset-0 z-[950] bg-slate-100 p-3 flex flex-col gap-2' : 'flex flex-col gap-2'} data-testid="fleet-map">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="sr-only">Live shipment map</h2>
        <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Filter by status">
          {chip('', 'All', data.vehicles.length)}
          {STATUSES.map((k) => chip(k, STATUS_LABEL[k].replace(', POD pending', ''), counts[k]))}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 ml-auto">
          <label className="relative"><span className="sr-only">Search shipment ID</span>
            <Icon name="search" size={14} className="absolute left-2 top-2 text-slate-400" />
            <input className="input !pl-7 w-36" placeholder="Search shipment ID" value={q} onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter' && vehicles[0]) onSelect(vehicles[0].id) }} />
          </label>
          <label><span className="sr-only">Filter by transporter</span>
            <select className="input !w-36" value={trans} onChange={(e) => setTrans(e.target.value)} aria-label="Filter by transporter"><option value="">Transporter: all</option>{transporters.map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></label>
          <label><span className="sr-only">Filter by risk category</span>
            <select className="input !w-28" value={risk} onChange={(e) => setRisk(e.target.value)} aria-label="Filter by risk category"><option value="">Risk: any</option><option value="HIGH">High risk</option><option value="MEDIUM">Medium risk</option><option value="LOW">Low risk</option></select></label>
        </div>
      </div>

      <div className={`relative rounded-lg overflow-hidden border border-slate-300 shadow-card ${full ? 'flex-1 min-h-0' : ''}`} style={full ? undefined : { height }}>
        <MapView ref={ref} height="100%" routes={routes} vehicles={vehicles} disruptions={data.disruptions} selectedId={selected}
          highlightRouteIds={highlight} showAlt={showAlt} showDisruptions={showDis} fitKey={fitKey} onSelect={(id) => onSelect(id)} caption={data.caption} />

        <div className="absolute left-3 top-3 z-[800] flex flex-col gap-1.5" role="toolbar" aria-label="Map tools" aria-orientation="vertical">
          <button className="fg-ctl" aria-label="Zoom in" title="Zoom in" onClick={() => ref.current?.zoomIn()}><Icon name="plus" size={16} /></button>
          <button className="fg-ctl" aria-label="Zoom out" title="Zoom out" onClick={() => ref.current?.zoomOut()}><Icon name="minus" size={16} /></button>
          <button className="fg-ctl mt-1" aria-label="Fit all shipments" title="Fit all shipments" onClick={() => ref.current?.fitAll()}><Icon name="fit" size={16} /></button>
          <button className="fg-ctl" aria-label="Centre on Plant X" title="Centre on Plant X" onClick={() => ref.current?.centerPlant()}><Icon name="factory" size={16} /></button>
          <button className="fg-ctl" aria-label="Centre on selected shipment" title="Centre on selected shipment" disabled={!selected} onClick={() => selected && ref.current?.centerOn(selected, 340)}><Icon name="target" size={16} /></button>
          <button className="fg-ctl mt-1" aria-label={showAlt ? 'Hide alternative routes' : 'Show alternative routes'} title={showAlt ? 'Hide alternative routes' : 'Show alternative routes'} aria-pressed={showAlt} onClick={() => setShowAlt(!showAlt)}><Icon name="route" size={16} /></button>
          <button className="fg-ctl" aria-label={showDis ? 'Hide disruptions' : 'Show disruptions'} title={showDis ? 'Hide disruptions' : 'Show disruptions'} aria-pressed={showDis} onClick={() => setShowDis(!showDis)}><Icon name="alert" size={16} /></button>
          <button className="fg-ctl mt-1" aria-label={full ? 'Exit full screen' : 'Full-screen map'} title={full ? 'Exit full screen (Esc)' : 'Full screen'} aria-pressed={full} onClick={() => setFull(!full)}><Icon name={full ? 'compress' : 'expand'} size={16} /></button>
        </div>

        <div className="absolute right-3 top-3 bottom-8 z-[800] flex flex-col items-end gap-2 pointer-events-none">
          {selShip && <div className="pointer-events-auto min-h-0 max-h-full"><Detail ship={selShip} vehicle={selVehicle} onClose={() => onSelect(null)} onCentre={() => ref.current?.centerOn(selShip.id, 340)} /></div>}
          <div className="mt-auto pointer-events-auto">
            {legend ? <Legend onClose={() => setLegend(false)} /> : <button className="btn-secondary btn-sm shadow-card" onClick={() => setLegend(true)} aria-expanded={false}><Icon name="layers" size={13} />Legend</button>}
          </div>
        </div>
      </div>
      <p className="text-[11px] text-slate-500">{data.caption} Positions are the last <em>reported</em> ones; grey, dashed trucks have stale data.</p>
    </div>
  )
}
