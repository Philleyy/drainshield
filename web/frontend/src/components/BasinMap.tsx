// A fixed map: OpenStreetMap background tiles, one dot per basin, and the run's route when there is one.
// shortcut: no map library and no pan/zoom, upgrade to Leaflet when people need to explore the other 5,000 basins.
// shortcut: OpenStreetMap's free public tile server (light use only), move to a paid tile provider before many users.
import { useNavigate } from 'react-router-dom'
import { useView } from '../view'

export interface MapPoint { id: string; lat: number; lon: number; category: string }
interface Props { points: MapPoint[]; line?: number[][]; stops?: { id: string; stop: number }[]; depot?: number[] }
export const CATEGORY_COLOR: Record<string, string> = { Urgent: '#c8312f', Inspect: '#e07a3f', Normal: '#2e9a5c', Offline: '#5a5f67' }
const TILE = 256

function worldPx(lat: number, lon: number, z: number) {
  const n = 2 ** z * TILE, rad = (lat * Math.PI) / 180
  return { x: ((lon + 180) / 360) * n, y: ((1 - Math.asinh(Math.tan(rad)) / Math.PI) / 2) * n }
}

export default function BasinMap({ points, line = [], stops = [], depot }: Props) {
  const navigate = useNavigate()
  const { dark } = useView()
  if (!points.length) return <p className="sub" style={{ padding: 16 }}>No monitored basin to show on the map yet.</p>
  const all = [...points.map(p => [p.lat, p.lon]), ...line, ...(depot ? [depot] : [])]
  let z = 15, box = { minX: 0, maxX: 0, minY: 0, maxY: 0 }
  for (; z >= 9; z--) {                                    // the closest zoom that keeps the picture under ~1800 px
    const px = all.map(([la, lo]) => worldPx(la, lo, z))
    box = { minX: Math.min(...px.map(p => p.x)), maxX: Math.max(...px.map(p => p.x)), minY: Math.min(...px.map(p => p.y)), maxY: Math.max(...px.map(p => p.y)) }
    if (box.maxX - box.minX < 1800 && box.maxY - box.minY < 1000) break
  }
  const pad = 90
  let { minX, maxX, minY, maxY } = { minX: box.minX - pad, maxX: box.maxX + pad, minY: box.minY - pad, maxY: box.maxY + pad }
  const wide = 1.7 * (maxY - minY)                         // keep a wide rectangle whatever the points
  if (maxX - minX < wide) { const add = (wide - (maxX - minX)) / 2; minX -= add; maxX += add }
  else { const add = ((maxX - minX) / 1.7 - (maxY - minY)) / 2; minY -= add; maxY += add }
  const tiles = []
  for (let tx = Math.floor(minX / TILE); tx <= Math.floor(maxX / TILE); tx++)
    for (let ty = Math.floor(minY / TILE); ty <= Math.floor(maxY / TILE); ty++)
      tiles.push(<image key={`${tx}-${ty}`} href={`https://tile.openstreetmap.org/${z}/${tx}/${ty}.png`}
        x={tx * TILE} y={ty * TILE} width={TILE + 0.5} height={TILE + 0.5} />)
  const scale = (maxX - minX) / 900                        // drawn sizes follow the zoom, so dots look the same
  const px = points.map(p => ({ ...p, ...worldPx(p.lat, p.lon, z) }))
  const stopOf = Object.fromEntries(stops.map(s => [s.id, s.stop]))
  const flagged = px.filter(p => p.category !== 'Normal')
  const d = depot && worldPx(depot[0], depot[1], z)
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`${minX} ${minY} ${maxX - minX} ${maxY - minY}`} style={{ display: 'block', width: '100%', height: 'auto', background: 'var(--bg)' }}
        role="group" aria-label={`Map of ${points.length} monitored basins, ${flagged.length} needing attention${stops.length ? `, with a route of ${stops.length} stops` : ''}`}>
        <g style={{ filter: dark ? 'invert(1) hue-rotate(180deg) saturate(0.3) brightness(0.9)' : 'saturate(0.3) brightness(1.03)' }}>{tiles}</g>
        {line.length > 1 && <polyline points={line.map(([la, lo]) => { const p = worldPx(la, lo, z); return `${p.x},${p.y}` }).join(' ')}
          fill="none" stroke="#1d5fd1" strokeWidth={3.5 * scale} strokeLinejoin="round" strokeLinecap="round" />}
        {d && <g><rect x={d.x - 9 * scale} y={d.y - 9 * scale} width={18 * scale} height={18 * scale} rx={4 * scale} fill="#14202b" stroke="#fff" strokeWidth={2 * scale} />
          <text x={d.x - 14 * scale} y={d.y + 5 * scale} textAnchor="end" fontFamily="Inter, sans-serif" fontSize={13 * scale} fontWeight={700} fill="var(--ink)" stroke="var(--surface)" strokeWidth={4 * scale} paintOrder="stroke">Yard</text></g>}
        {[...px].sort((a, b) => Number(a.category !== 'Normal') - Number(b.category !== 'Normal')).map(p => {
          const n = stopOf[p.id], big = p.category !== 'Normal' || n != null
          return (
            <g key={p.id} role="link" tabIndex={0} aria-label={`${p.id}: ${p.category}${n != null ? `, stop ${n}` : ''}`} style={{ cursor: 'pointer' }}
              onClick={() => navigate(`/basins/${p.id}`)}
              onKeyDown={e => { if (e.key === 'Enter') navigate(`/basins/${p.id}`) }}>
              <circle cx={p.x} cy={p.y} r={(big ? 12 : 7) * scale} fill={CATEGORY_COLOR[p.category] || '#5a5f67'} stroke="#fff" strokeWidth={2.5 * scale} />
              {n != null && <text x={p.x} y={p.y + 4.5 * scale} textAnchor="middle" fontFamily="Inter, sans-serif" fontSize={13 * scale} fontWeight={700} fill="#fff">{n}</text>}
              {big && <text x={p.x + 17 * scale} y={p.y + 5 * scale} fontFamily="Inter, sans-serif" fontSize={14 * scale} fontWeight={700} fill="var(--ink)"
                stroke="var(--surface)" strokeWidth={4 * scale} paintOrder="stroke">{p.id}</text>}
            </g>
          )
        })}
      </svg>
      <figcaption className="map-legend">
        {Object.entries({ Urgent: 'Urgent', Inspect: 'Inspect soon', Normal: 'Draining normally', Offline: 'Sensor offline' }).map(([k, v]) => (
          <span key={k}><i style={{ background: CATEGORY_COLOR[k] }} />{v}</span>
        ))}
        {stops.length > 0 && <span>1 2 3 = stop order</span>}
        <span style={{ marginLeft: 'auto' }}>© OpenStreetMap contributors</span>
      </figcaption>
    </figure>
  )
}
