// The basins on a real map (Leaflet + OpenStreetMap tiles): zoom and pan, one pin per basin, the run's route.
// The map is created once and only its pins are redrawn, so the 5-second refresh never reloads the tiles.
// shortcut: OpenStreetMap's free public tile server (light use only), move to a paid tile provider before many users.
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { t } from '../i18n'
import { useView } from '../view'

export interface MapPoint { id: string; lat: number; lon: number; category: string }
interface Props {
  points: MapPoint[]; line?: number[][]; stops?: { id: string; stop: number }[]; depot?: number[]
  others?: { id: string; lat: number; lon: number }[]               // the city's basins without a sensor
  selected?: string | null; onSelect?: (id: string) => void          // without onSelect, a pin opens its basin
  onPickCity?: (id: string) => void                                  // without it, a grey dot opens the add form
  preview?: { lat: number; lon: number } | null                      // a basin being added
  height?: string; legend?: boolean
}
export const CATEGORY_COLOR: Record<string, string> = { Urgent: '#c8312f', Inspect: '#e07a3f', Normal: '#2e9a5c', Offline: '#5a5f67' }
const LEGEND: Record<string, string> = { Urgent: 'Urgent', Inspect: 'Inspect soon', Normal: 'Draining normally', Offline: 'Sensor offline' }
const DORVAL: L.LatLngTuple = [45.448, -73.75]
const FIT: L.FitBoundsOptions = { padding: [40, 40], maxZoom: 16 }
const median = (xs: number[]) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)]
const esc = (s: string) => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))

/** Basins placed far from the rest (a 0, 0 left from a test, a typo) would zoom the map out to the whole planet:
 * they stay off the map and are listed under it instead. */
function placed(points: MapPoint[]) {
  const ok = points.filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lon) && !(p.lat === 0 && p.lon === 0))
  if (!ok.length) return { onMap: ok, away: points, near: () => true }
  const lat = median(ok.map(p => p.lat)), lon = median(ok.map(p => p.lon))
  const near = (la: number, lo: number) => Math.abs(la - lat) < 0.5 && Math.abs(lo - lon) < 0.7        // about 50 km
  return { onMap: ok.filter(p => near(p.lat, p.lon)), away: points.filter(p => !ok.includes(p) || !near(p.lat, p.lon)), near }
}

function pin(html: string) { return L.divIcon({ className: 'map-pin', html, iconSize: [0, 0] }) }

export default function BasinMap({ points: given, line = [], stops = [], depot, others = [], selected = null, onSelect, onPickCity, preview = null, height = 'clamp(360px, 60vh, 640px)', legend = true }: Props) {
  const navigate = useNavigate()
  const { dark } = useView()
  const box = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const groups = useRef<{ city: L.LayerGroup; route: L.LayerGroup; basins: L.LayerGroup } | null>(null)
  const framed = useRef('')
  const fitTo = useRef<L.LatLngBounds | null>(null)        // what to keep in view while the person hasn't moved the map
  const act = useRef({ onSelect, onPickCity, navigate })
  act.current = { onSelect, onPickCity, navigate }
  const { onMap, away, near } = placed(given)

  useEffect(() => {
    const m = L.map(box.current!, { preferCanvas: true, scrollWheelZoom: false }).setView(DORVAL, 14)
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(m)
    m.on('focus', () => m.scrollWheelZoom.enable())          // the wheel zooms only after a click, so the page still scrolls
    m.on('blur', () => m.scrollWheelZoom.disable())
    groups.current = { city: L.layerGroup().addTo(m), route: L.layerGroup().addTo(m), basins: L.layerGroup().addTo(m) }
    map.current = m
    const touched = () => { fitTo.current = null }
    box.current!.addEventListener('pointerdown', touched)
    box.current!.addEventListener('wheel', touched)
    const resized = new ResizeObserver(() => {
      m.invalidateSize()
      if (fitTo.current) m.fitBounds(fitTo.current, FIT)
    })
    resized.observe(box.current!)
    return () => { resized.disconnect(); m.remove(); map.current = null }
  }, [])

  const monitored = new Set(given.map(p => p.id))
  useEffect(() => {
    const g = groups.current!
    g.city.clearLayers()
    for (const o of others) {
      if (monitored.has(o.id) || !near(o.lat, o.lon)) continue
      L.circleMarker([o.lat, o.lon], { radius: 4, color: '#fff', weight: 1, fillColor: '#8a949d', fillOpacity: 0.85 })
        .bindTooltip(t('City basin {id}: click to add a sensor', { id: o.id }))
        .on('click', () => { const a = act.current; if (a.onPickCity) a.onPickCity(o.id); else a.navigate(`/basins?city=${o.id}`) })
        .addTo(g.city)
    }
  }, [others, given])   // eslint-disable-line react-hooks/exhaustive-deps

  const stopOf = Object.fromEntries(stops.map(s => [s.id, s.stop]))
  const key = JSON.stringify([onMap.map(p => [p.id, p.category]), line.length, stops, depot, selected, preview])
  useEffect(() => {
    const m = map.current!, g = groups.current!
    g.route.clearLayers(); g.basins.clearLayers()
    const route = line.filter(([la, lo]) => near(la, lo))
    if (route.length > 1) L.polyline(route as L.LatLngTuple[], { color: '#1d5fd1', weight: 4, opacity: 0.85 }).addTo(g.route)
    if (depot) L.marker(depot as L.LatLngTuple, { icon: pin(`<span class="pin depot"></span><span class="pin-label">${t('Yard')}</span>`), keyboard: false, interactive: false }).addTo(g.route)
    for (const p of [...onMap].sort((a, b) => Number(a.category !== 'Normal') - Number(b.category !== 'Normal'))) {
      const n = stopOf[p.id], flagged = p.category !== 'Normal', on = p.id === selected
      const html = `<span class="pin${flagged || n != null ? ' big' : ''}${on ? ' on' : ''}" style="background:${CATEGORY_COLOR[p.category] || '#5a5f67'}">${n ?? ''}</span>`
        + (flagged || n != null || on ? `<span class="pin-label">${esc(p.id)}</span>` : '')
      L.marker([p.lat, p.lon], { icon: pin(html), title: `${p.id}: ${t(LEGEND[p.category] || p.category)}`, zIndexOffset: on ? 1000 : flagged ? 500 : 0 })
        .on('click', () => { const a = act.current; if (a.onSelect) a.onSelect(p.id); else a.navigate(`/basins/${p.id}`) })
        .addTo(g.basins)
    }
    if (preview) L.marker([preview.lat, preview.lon], { icon: pin(`<span class="pin big preview"></span><span class="pin-label">${t('New basin')}</span>`), zIndexOffset: 2000, interactive: false }).addTo(g.basins)

    // frame the basins when they change, not on every refresh, so a zoom or pan by the person stays put
    const frame = onMap.map(p => p.id).join(',')
    if (frame !== framed.current) {
      framed.current = frame
      const pts: L.LatLngTuple[] = [...onMap.map(p => [p.lat, p.lon] as L.LatLngTuple), ...(depot && onMap.length ? [depot as L.LatLngTuple] : [])]
      if (pts.length) { fitTo.current = L.latLngBounds(pts); m.fitBounds(fitTo.current, FIT) }
    }
    const sel = onMap.find(p => p.id === selected)
    if (sel && !m.getBounds().contains([sel.lat, sel.lon])) m.panTo([sel.lat, sel.lon])
  }, [key])   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                                        // follow the position typed or picked in the add form
    if (preview && Number.isFinite(preview.lat) && Number.isFinite(preview.lon)) fitTo.current = null
    if (preview && Number.isFinite(preview.lat) && Number.isFinite(preview.lon)) map.current!.setView([preview.lat, preview.lon], Math.max(map.current!.getZoom(), 17))
  }, [preview?.lat, preview?.lon])   // eslint-disable-line react-hooks/exhaustive-deps

  const flagged = onMap.filter(p => p.category !== 'Normal').length
  return (
    <figure style={{ margin: 0 }}>
      {away.length > 0 && <p className="notice" style={{ margin: 12 }}>
        {t('Not on the map (position missing or far from the others): {ids}. Open the basin and save it again with its real latitude and longitude.', { ids: away.map(p => p.id).join(', ') })}</p>}
      <div ref={box} className={`map-box${dark ? ' map-dark' : ''}`} style={{ height }} role="region"
        aria-label={`${t('Map of {n} monitored basins, {k} needing attention', { n: onMap.length, k: flagged })}${stops.length ? t(', with a route of {n} stops', { n: stops.length }) : ''}`} />
      {legend && <figcaption className="map-legend">
        {Object.entries(LEGEND).map(([k, v]) => <span key={k}><i style={{ background: CATEGORY_COLOR[k] }} />{t(v)}</span>)}
        {others.length > 0 && <span><i style={{ background: '#8a949d' }} />{t('No sensor (click to add one)')}</span>}
        {stops.length > 0 && <span>{t('1 2 3 = stop order')}</span>}
      </figcaption>}
    </figure>
  )
}
