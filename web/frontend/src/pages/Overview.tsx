import { useState } from 'react'
import BasinMap from '../components/BasinMap'
import BasinTable, { type BasinRow } from '../components/BasinTable'
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
  const [all, setAll] = useState(false)
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">Loading…</p>

  const f = data.forecast
  const toRain = f.starts ? minutesBetween(data.now, f.starts) : null
  const flagged = data.basins.filter(b => b.category !== 'Normal')
  const beforeStorm = data.basins.filter(b => b.priority === 'Inspect before storm').length
  const plan = data.run.suggested, sent = data.run.sent
  const stops = plan ? plan.stops : sent ? sent.stops : []

  return (
    <>
      <section className="card" aria-label="Storm timeline">
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
        {f.hours.length > 0 && <StormTimeline rain={f.hours} nowIso={data.now} minutesToRain={f.heavy ? toRain : null}
          run={plan ? { from: fromNow(data.now, plan.leave), to: fromNow(data.now, plan.leave) + plan.drive_min + plan.service_min, label: `Run · ${plan.leave}–${plan.back}` } : undefined} />}
      </section>

      <section className="grid-kpi" aria-label="Network status">
        {([['Urgent', 'Urgent', 'var(--urgent-text)'], ['Inspect', 'Inspect soon', 'var(--inspect-text)'], ['Offline', 'Sensor offline', 'var(--offline-text)'], ['Normal', 'Draining normally', 'var(--normal-text)']] as const).map(([c, label, color]) => (
          <div className="card" key={c}>
            <div className="eyebrow">{label}</div>
            <div className="big" style={{ color: data.counts[c] ? color : 'var(--ink)' }}>{data.counts[c]}</div>
          </div>
        ))}
      </section>

      {data.basins.length === 0 ? (
        <section className="card">
          <h2>No monitored basin yet</h2>
          <p className="sub">Add a basin under <b>Basins</b>, then start a bridge with an upload key so its sensor sends readings here.
            To see the product with data, switch <b>Data</b> to <b>Pitch demo</b> in the menu.</p>
        </section>
      ) : <>
        <div className="split" style={{ alignItems: 'stretch' }}>
          <section className="card flush" aria-label="Map" style={{ flex: '999 1 520px', minWidth: 0 }}>
            <BasinMap points={data.basins} line={plan?.line || sent?.line} stops={stops} depot={plan?.depot || sent?.depot} />
          </section>
          <div style={{ flex: '1 1 340px', maxWidth: 460, display: 'flex' }}><RunSummary run={data.run} /></div>
        </div>

        <section className="card flush" aria-label="Basins">
          <div className="card-head">
            <h2>{all ? 'All monitored basins' : 'Needs action'}</h2>
            <button type="button" className="btn small" onClick={() => setAll(!all)}>{all ? 'Only those needing action' : `Show all ${data.basins.length}`}</button>
          </div>
          {!all && flagged.length === 0
            ? <p className="sub" style={{ padding: '4px 16px 16px' }}>Nothing needs attention: all {data.basins.length} basins are draining normally.</p>
            : <BasinTable rows={all ? data.basins : flagged} />}
        </section>
      </>}
    </>
  )
}
