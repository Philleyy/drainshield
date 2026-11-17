import { useEffect, useRef, useState } from 'react'
import { cityBasins, type CityBasin } from '../city'
import BasinMap from '../components/BasinMap'
import BasinTable, { chipClass, type BasinRow } from '../components/BasinTable'
import { StormTimeline, type RainBar } from '../components/Charts'
import RunSummary, { type RunState } from '../components/Run'
import { clock, duration, minutesBetween, useData } from '../view'

interface Forecast { available: boolean; total_mm?: number; max_mm_h?: number; starts?: string | null; heavy?: boolean; hours: RainBar[] }
export interface OverviewData { now: string; forecast: Forecast; counts: Record<string, number>; basins: BasinRow[]; run: RunState }

function headline(f: Forecast, toRain: number | null) {
  if (!f.available) return 'Forecast unavailable right now'
  if ((f.hours[0]?.mm || 0) > 0) return `Raining now: ${f.hours[0].mm} mm this hour, ${Math.round(f.total_mm!)} mm in the next 12 h`
  if (f.total_mm! < 0.5 || toRain == null) return 'No significant rain in the next 12 hours'
  return `${f.heavy ? 'Storm' : 'Rain'} at ${clock(f.starts!)}: ${Math.round(f.total_mm!)} mm, up to ${Math.round(f.max_mm_h!)} mm/h`
}
/** Minutes from now until a clock time today (or tomorrow if it has passed). */
const fromNow = (nowIso: string, hhmm: string) => (Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3)) - Number(nowIso.slice(11, 13)) * 60 - Number(nowIso.slice(14, 16)) + 1440) % 1440

export default function Overview() {
  const { data, error } = useData<OverviewData>('/overview')
  const [filter, setFilter] = useState<string | null>(null)             // a category, 'All', or null = needs action
  const table = useRef<HTMLElement>(null)
  const [showCity, setShowCity] = useState(false)
  const [city, setCity] = useState<CityBasin[]>([])
  useEffect(() => { if (showCity) cityBasins().then(setCity).catch(() => setCity([])) }, [showCity])
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const f = data.forecast
  const toRain = f.starts ? minutesBetween(data.now, f.starts) : null
  const flagged = data.basins.filter(b => b.category !== 'Normal')
  const shown = filter === 'All' ? data.basins : filter ? data.basins.filter(b => b.category === filter) : flagged
  const pick = (f: string) => { setFilter(filter === f ? null : f); table.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }) }
  const beforeStorm = data.basins.filter(b => b.priority === 'Inspect before storm').length
  const plan = data.run.suggested, sent = data.run.sent
  const stops = plan ? plan.stops : sent ? sent.stops : []

  return (
    <>
      <section className="hero" aria-label="Storm timeline">
        <div className="row" style={{ alignItems: 'flex-end', gap: 20 }}>
          <div style={{ flex: '1 1 380px' }}>
            <div className="eyebrow">Next 36 hours · Environment Canada GEM</div>
            <h1 style={{ marginTop: 6 }}>{headline(f, toRain)}</h1>
          </div>
          {f.heavy && toRain != null && toRain > 0 && <>
            <div><div className="big" style={{ color: 'var(--window)' }}>{duration(toRain)}</div><div className="sub" style={{ margin: 0 }}>safe cleaning window</div></div>
            <div><div className="big">{beforeStorm}</div><div className="sub" style={{ margin: 0 }}>{beforeStorm === 1 ? 'basin' : 'basins'} to clean first</div></div>
          </>}
        </div>
        {f.hours.length > 0 && <div className="chart-scroll"><StormTimeline rain={f.hours} nowIso={data.now} minutesToRain={f.heavy ? toRain : null}
          run={plan ? { from: fromNow(data.now, plan.leave), to: fromNow(data.now, plan.leave) + plan.drive_min + plan.service_min, label: `Run · ${plan.leave}–${plan.back}` } : undefined} /></div>}
      </section>

      <nav className="triage" aria-label="Filter the basins by status">
        {([['Urgent', 'Urgent'], ['Inspect', 'Inspect soon'], ['Offline', 'Sensor offline'], ['Normal', 'Draining normally']] as const).map(([c, label]) => (
          <button key={c} type="button" className={`pill ${chipClass(c)}`} aria-pressed={filter === c} onClick={() => pick(c)} disabled={!data.counts[c]}>
            <b>{data.counts[c]}</b>{label}
          </button>
        ))}
        <button type="button" className="pill" aria-pressed={filter === 'All'} onClick={() => pick('All')}><b>{data.basins.length}</b>All basins</button>
      </nav>

      {data.basins.length === 0 ? (
        <section className="card">
          <h2>No monitored basin yet</h2>
          <p className="sub">Add a basin under <b>Basins</b>, then start a bridge with an upload key so its sensor sends readings here.
            To see the product with data, switch <b>Data</b> to <b>Pitch demo</b> in the menu.</p>
        </section>
      ) : <>
        <div className="split" style={{ alignItems: 'stretch' }}>
          <section className="card flush" aria-label="Map" style={{ flex: '999 1 520px', minWidth: 0 }}>
            <BasinMap points={data.basins} line={plan?.line || sent?.line} stops={stops} depot={plan?.depot || sent?.depot} others={showCity ? city : []} />
            <label className="check" style={{ padding: '10px 14px', borderTop: '1px solid var(--hairline)' }}>
              <input type="checkbox" checked={showCity} onChange={e => setShowCity(e.target.checked)} />Show the city's other catch basins in this view (no sensor yet)
            </label>
          </section>
          <div style={{ flex: '1 1 340px', maxWidth: 460, display: 'flex' }}><RunSummary run={data.run} /></div>
        </div>

        <section className="card flush" aria-label="Basins" ref={table} style={{ scrollMarginTop: 16 }}>
          <div className="card-head">
            <h2>{filter === 'All' ? 'All monitored basins' : filter ? `${shown.length} × ${filter === 'Inspect' ? 'inspect soon' : filter.toLowerCase()}` : 'Needs action'}</h2>
            {filter && <button type="button" className="btn small" onClick={() => setFilter(null)}>Back to needs action</button>}
          </div>
          {shown.length === 0
            ? <p className="sub" style={{ padding: '4px 16px 16px' }}>Nothing needs attention: all {data.basins.length} basins are draining normally.</p>
            : <BasinTable rows={shown} />}
        </section>
      </>}
    </>
  )
}
