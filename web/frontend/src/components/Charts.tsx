// Hand-drawn SVG charts (no chart library): the storm timeline, a basin's day, and its cross-section.
import { clock } from '../view'

export interface RainBar { t: string; mm: number }
// colours come from the theme (styles.css), so the charts follow light / dark
const INK = 'var(--ink)', MUTED = 'var(--muted)', RAIN = 'var(--rain)', GRID = 'var(--grid)', AXIS = 'var(--axis)'
const text = { fontSize: 12, fill: MUTED } as const

/** Next 36 h of rain, hour by hour, with the dry window before it shaded. */
export function StormTimeline({ rain, nowIso, minutesToRain, run }: { rain: RainBar[]; nowIso: string; minutesToRain: number | null; run?: { from: number; to: number; label: string } }) {
  const W = 1080, x0 = 24, base = 170, top = 46, step = (W - 2 * x0) / Math.max(rain.length, 1)
  const max = Math.max(12, ...rain.map(r => r.mm))
  const nowX = x0 + (Number(nowIso.slice(14, 16)) / 60) * step
  const windowW = minutesToRain && minutesToRain > 0 ? (minutesToRain / 60) * step : 0
  const wet = rain.filter(r => r.mm > 0)
  return (
    <svg viewBox={`0 0 ${W} 208`} style={{ display: 'block', width: '100%', height: 'auto' }} role="img"
      aria-label={wet.length ? `Hourly rain forecast: ${wet.map(r => `${clock(r.t)} ${r.mm} mm`).join(', ')}` : 'No rain in the next 36 hours'}>
      {windowW > 0 && <>
        <rect x={nowX} y={20} width={windowW} height={base - 20} fill="var(--window-tint)" />
        <text x={nowX + 8} y={38} {...text} fontWeight={600} fill="var(--window)">Safe cleaning window</text>
      </>}
      <line x1={x0} y1={(base + top) / 2} x2={W - x0} y2={(base + top) / 2} stroke={GRID} />
      <line x1={x0} y1={top} x2={W - x0} y2={top} stroke={GRID} />
      <text x={W - x0} y={top - 4} textAnchor="end" {...text} fontSize={11}>{max} mm/h</text>
      <line x1={x0} y1={base} x2={W - x0} y2={base} stroke={AXIS} />
      {rain.map((r, i) => {
        const h = (r.mm / max) * (base - top), x = x0 + i * step
        return (
          <g key={r.t}>
            {r.mm > 0 && <rect x={x + 3} y={base - h} width={step - 6} height={h} rx={4} fill={RAIN} />}
            {r.mm > 0 && <text x={x + step / 2} y={base - h - 6} textAnchor="middle" {...text} fontWeight={600} fill={INK}>{r.mm}</text>}
            {i % 3 === 0 && i > 0 && <text x={x} y={base + 20} textAnchor="middle" {...text}>{clock(r.t)}</text>}
          </g>
        )
      })}
      {run && <>  {/* drawn after the rain bars so its label stays readable */}
        <rect x={nowX + (run.from / 60) * step} y={base - 30} width={Math.max(((run.to - run.from) / 60) * step, 6)} height={14} rx={4} fill="var(--accent)" />
        <text x={nowX + (run.to / 60) * step + 6} y={base - 19} {...text} fontWeight={600} fill="var(--link)" stroke="var(--bg)" strokeWidth={4} paintOrder="stroke">{run.label}</text>
      </>}
      <line x1={nowX} y1={14} x2={nowX} y2={base + 6} stroke={INK} strokeWidth={2} />
      <text x={nowX} y={base + 34} textAnchor="middle" {...text} fontWeight={700} fill={INK}>Now</text>
    </svg>
  )
}

/** One basin's day: rain on top, water level below, same time axis (two panels, never two scales on one). */
export function DayChart({ rain, levels, nowIso }: { rain: RainBar[]; levels: { t: string; cm: number }[]; nowIso: string }) {
  const W = 1000, x0 = 56, x1 = W - 30, rTop = 20, rBase = 80, lTop = 110, lBase = 270
  const minuteOf = (iso: string) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16))
  const x = (m: number) => x0 + (m / 1440) * (x1 - x0)
  const rMax = Math.max(12, ...rain.map(r => r.mm)), lMax = Math.max(40, ...levels.map(l => l.cm))
  const lMin = Math.min(0, ...levels.map(l => l.cm))                  // below 0 = sump emptied by the vacuum truck
  const y = (cm: number) => lBase - ((cm - lMin) / (lMax - lMin)) * (lBase - lTop)
  const nowM = minuteOf(nowIso)
  const path = levels.map((l, i) => `${i ? 'L' : 'M'}${x(minuteOf(l.t)).toFixed(1)} ${y(l.cm).toFixed(1)}`).join(' ')
  const peak = levels.reduce((a, l) => (l.cm > a.cm ? l : a), { t: '', cm: 0 })
  return (
    <svg viewBox={`0 0 ${W} 314`} style={{ display: 'block', width: '100%', height: 'auto' }} role="img"
      aria-label={`Rain and water level today. Highest water so far: ${peak.cm} cm above the outlet${peak.t ? ` at ${clock(peak.t)}` : ''}.`}>
      <text x={x0} y={rTop - 6} {...text}>Rain (mm in each hour)</text>
      <line x1={x0} y1={rBase} x2={x1} y2={rBase} stroke={AXIS} />
      {rain.map(r => r.mm > 0 && (
        <g key={r.t}>
          <rect x={x(minuteOf(r.t)) + 2} y={rBase - (r.mm / rMax) * (rBase - rTop)} width={(x1 - x0) / 24 - 4}
            height={(r.mm / rMax) * (rBase - rTop)} rx={3} fill={RAIN} opacity={minuteOf(r.t) > nowM ? 0.45 : 1} />
          <text x={x(minuteOf(r.t) + 30)} y={rBase - (r.mm / rMax) * (rBase - rTop) - 4} textAnchor="middle" {...text} fontSize={11}>{r.mm}</text>
        </g>
      ))}
      <text x={x0} y={lTop - 8} {...text}>Water above the outlet (cm)</text>
      {[...(lMin < 0 ? [lMin] : []), 0, lMax / 2, lMax].map(v => (
        <g key={v}>
          <line x1={x0} y1={y(v)} x2={x1} y2={y(v)} stroke={v ? GRID : AXIS} />
          <text x={x0 - 6} y={y(v) + 4} textAnchor="end" {...text} fontSize={11}>{Math.round(v)}</text>
        </g>
      ))}
      {path && <path d={path} fill="none" stroke="var(--link)" strokeWidth={2.5} strokeLinejoin="round" />}
      {peak.cm >= 5 && <text x={x(minuteOf(peak.t))} y={y(peak.cm) - 8} textAnchor="middle" {...text} fontWeight={600} fill={INK}>{peak.cm} cm at {clock(peak.t)}</text>}
      {[0, 3, 6, 9, 12, 15, 18, 21, 24].map(h => <text key={h} x={x(h * 60)} y={lBase + 20} textAnchor="middle" {...text}>{String(h % 24).padStart(2, '0')}:00</text>)}
      <line x1={x(nowM)} y1={rTop} x2={x(nowM)} y2={lBase} stroke={INK} strokeWidth={1.5} strokeDasharray="4 4" />
      <text x={x(nowM)} y={lBase + 36} textAnchor="middle" {...text} fontWeight={700} fill={INK}>Now</text>
    </svg>
  )
}

export interface Dims { inner_width_cm: number; invert_depth_cm: number; sump_depth_cm: number; outlet_diameter_cm: number; sensor_depth_cm: number }

/** The basin drawn to scale from its as-built depths, with the live water level. */
export function CrossSection({ d, levelCm, sedimentPct, restriction, estimated }: { d: Dims; levelCm: number | null; sedimentPct: number | null; restriction?: string | null; estimated?: boolean }) {
  const s = 2.3, top = 34, floor = d.invert_depth_cm + d.sump_depth_cm
  const y = (depthCm: number) => top + depthCm * s
  const xl = 120, w = d.inner_width_cm * s, xr = xl + w, wall = 22
  const waterTop = levelCm == null ? null : y(Math.min(Math.max(d.invert_depth_cm - levelCm, 0), floor))
  const sedH = ((sedimentPct || 0) / 100) * d.sump_depth_cm * s
  const m = (cm: number) => (cm / 100).toFixed(2)
  const lx = xr + wall + 90
  const label = (depth: number, t: string) => (
    <g key={t}>
      <line x1={xr + wall} y1={y(depth)} x2={lx - 6} y2={y(depth)} stroke="#9aa5ae" strokeDasharray="3 3" />
      <text x={lx} y={y(depth) + 5} fontSize={15} fill={INK}>{t}</text>
    </g>
  )
  return (
    <svg viewBox={`0 0 ${lx + (estimated ? 470 : 300)} ${y(floor) + 40}`} style={{ display: 'block', width: '100%', maxWidth: 700, height: 'auto', margin: '0 auto' }} role="img"
      aria-label={`Cross-section: sensor ${m(d.sensor_depth_cm)} m below the street, outlet at ${m(d.invert_depth_cm)} m, sump floor at ${m(floor)} m. ${levelCm == null ? 'No current water reading.' : `Water ${m(Math.max(d.invert_depth_cm - levelCm, 0))} m below the street.`}`}>
      <rect x={xl - wall - 40} y={top} width={w + 2 * wall + 80} height={y(floor) - top + 20} fill="#efe8dc" />
      <rect x={xl} y={top + 8} width={w} height={y(floor) - top - 8} fill="#fbfbfc" />
      {waterTop != null && <rect x={xl} y={waterTop} width={w} height={y(floor) - waterTop} fill="#7fb2e5" />}
      {waterTop != null && <line x1={xl} y1={waterTop} x2={xr} y2={waterTop} stroke="#1d5fd1" strokeWidth={2.5} />}
      {sedH > 1 && <rect x={xl} y={y(floor) - sedH} width={w} height={sedH} fill="#9b7a52" />}
      <rect x={xl - wall} y={top} width={wall} height={y(floor) - top + 16} fill="#c9c6bf" />
      <rect x={xr} y={top} width={wall} height={y(floor) - top + 16} fill="#c9c6bf" />
      <rect x={xl - wall} y={y(floor)} width={w + 2 * wall} height={16} fill="#a9a59c" />
      <rect x={xl - wall - 8} y={top - 4} width={w + 2 * wall + 16} height={10} fill="#3a3f45" />
      <rect x={xr} y={y(d.invert_depth_cm - d.outlet_diameter_cm)} width={wall + 60} height={d.outlet_diameter_cm * s} fill="#d8d5ce" stroke="#a9a59c" strokeWidth={2} />
      <path d={`M${xl} ${y(d.sensor_depth_cm) - 10} L${xl + 24} ${y(d.sensor_depth_cm) - 10} L${xl} ${y(d.sensor_depth_cm) + 12} Z`} fill={INK} />
      {label(0, '0.00 m · Street grate')}
      {label(d.sensor_depth_cm, `−${m(d.sensor_depth_cm)} m · Sensor`)}
      {label(d.invert_depth_cm, `${estimated ? '≈ ' : ''}−${m(d.invert_depth_cm)} m · Outlet ø${d.outlet_diameter_cm * 10}${estimated ? ' (guess until the sensor learns it)' : ''}`)}
      {label(floor, `${estimated ? '≈ ' : ''}−${m(floor)} m · Sump floor`)}
      {waterTop != null && <text x={xl + w / 2} y={waterTop - 8} textAnchor="middle" fontSize={15} fontWeight={600} fill="#1d4aa8">−{m(Math.max(d.invert_depth_cm - (levelCm || 0), 0))} m</text>}
      {sedH > 14 && <text x={xl + w / 2} y={y(floor) - sedH / 2 + 5} textAnchor="middle" fontSize={13} fontWeight={600} fill="#fff">sediment ~{Math.round(sedimentPct || 0)}%</text>}
      {restriction && <text x={lx} y={y(d.invert_depth_cm) + 26} fontSize={14} fontWeight={600} fill="var(--inspect-text)">{restriction}</text>}
    </svg>
  )
}
