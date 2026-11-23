import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { cityBasins, type CityBasin } from '../city'
import BasinMap from '../components/BasinMap'
import BasinList, { countLine, MapCard, toHandle } from '../components/BasinList'
import { type BasinRow, type Check } from '../components/BasinTable'
import { StormTimeline, type RainBar } from '../components/Charts'
import RunSummary, { type RunState } from '../components/Run'
import StormPanel, { type Storm } from '../components/Storm'
import { plural, t } from '../i18n'
import { clock, day, duration, minutesBetween, useData } from '../view'

interface Forecast { available: boolean; total_mm?: number; max_mm_h?: number; starts?: string | null; heavy?: boolean; hours: RainBar[] }
export interface Season { key: 'spring' | 'summer' | 'fall' | 'winter'; risk: boolean; heavy_mm: number; dry_every_min: number }
export interface OverviewData {
  now: string; forecast: Forecast; counts: Record<string, number>; basins: BasinRow[]; run: RunState
  season: Season; storm: Storm; checks: (Check & { id: string; address: string })[]
}

function headline(f: Forecast, toRain: number | null) {
  if (!f.available) return t('Forecast unavailable right now')
  if ((f.hours[0]?.mm || 0) > 0) return t('Raining now: {mm} mm this hour, {total} mm in the next 12 h', { mm: f.hours[0].mm, total: Math.round(f.total_mm!) })
  if (f.total_mm! < 0.5 || toRain == null) return t('No significant rain in the next 12 hours')
  return t(f.heavy ? 'Storm at {time}: {mm} mm, up to {max} mm/h' : 'Rain at {time}: {mm} mm, up to {max} mm/h',
    { time: clock(f.starts!), mm: Math.round(f.total_mm!), max: Math.round(f.max_mm_h!) })
}
/** Minutes from now until a clock time today (or tomorrow if it has passed). */
const fromNow = (nowIso: string, hhmm: string) => (Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3)) - Number(nowIso.slice(11, 13)) * 60 - Number(nowIso.slice(14, 16)) + 1440) % 1440

const SEASON: Record<Season['key'], string> = {
  spring: 'Spring: snowmelt carries road grit into the basins', summer: 'Summer', fall: 'Fall: leaves on the grates',
  winter: 'Winter: sensors read less often to save battery',
}
export function seasonLine(s: Season) {
  return `${t(SEASON[s.key])} · ${t(s.risk ? 'storms of {mm} mm or more trigger a pre-storm run' : 'pre-storm run from {mm} mm', { mm: s.heavy_mm })} · ${t('dry-weather readings every {min} min', { min: s.dry_every_min })}`
}

const CHECK: Record<Check['state'], { chip: string; text: string }> = {
  still_slow: { chip: 'inspect', text: 'Still slow: check again' },
  waiting: { chip: 'plain', text: 'Waiting for rain' },
  confirmed: { chip: 'normal', text: 'Cleaning confirmed' },
}
export const checkText = (c: Check) => t(CHECK[c.state].text)

/** After each cleaning, the next rain shows whether the basin drains normally again: a confirmation for the City. */
function Checks({ checks }: { checks: OverviewData['checks'] }) {
  const n = (s: Check['state']) => checks.filter(c => c.state === s).length
  return (
    <section className="card flush" aria-label={t('Cleaning checks')}>
      <div className="card-head">
        <h2>{t('Cleaning checks · last 30 days')}</h2>
        <span className="chip normal">{plural(n('confirmed'), '{n} basin confirmed', '{n} basins confirmed')}</span>
        <span className="chip plain">{plural(n('waiting'), '{n} basin waiting for rain', '{n} basins waiting for rain')}</span>
        {n('still_slow') > 0 && <span className="chip inspect">{plural(n('still_slow'), '{n} basin still slow', '{n} basins still slow')}</span>}
      </div>
      <p className="sub" style={{ padding: '10px 16px 0' }}>{t('The first rain after a cleaning shows whether the basin drains normally again. A confirmation for the City, with nothing for the crew to fill in.')}</p>
      <div className="table-wrap"><table>
        <thead><tr><th>{t('Basin')}</th><th>{t('Cleaned')}</th><th>{t('Next rain')}</th><th>{t('Result')}</th></tr></thead>
        <tbody>
          {checks.map(c => (
            <tr key={c.id}>
              <td><Link to={`/basins/${c.id}`} style={{ fontWeight: 600 }}>{c.id}</Link><small>{c.address}</small></td>
              <td>{day(c.cleaned_at)}, {clock(c.cleaned_at)}</td>
              <td>{c.rain_at ? `${day(c.rain_at)}, ${clock(c.rain_at)}` : '—'}</td>
              <td><span className={`chip ${CHECK[c.state].chip}`}>{checkText(c)}</span></td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </section>
  )
}

export default function Overview() {
  const { data, error } = useData<OverviewData>('/overview')
  const [selected, setSelected] = useState<string | null>(null)
  const [showCity, setShowCity] = useState(false)
  const [city, setCity] = useState<CityBasin[]>([])
  useEffect(() => { if (showCity) cityBasins().then(setCity).catch(() => setCity([])) }, [showCity])
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">{t('Loading…')}</p>

  const f = data.forecast
  const toRain = f.starts ? minutesBetween(data.now, f.starts) : null
  const todo = toHandle(data.basins)
  const plan = data.run.suggested, sent = data.run.sent
  const stops = plan ? plan.stops : sent ? sent.stops : []
  const picked = data.basins.find(b => b.id === selected) || null
  const confirmed = data.checks.filter(c => c.state === 'confirmed').length

  return (
    <>
      {data.storm.alerts.length > 0 && <StormPanel storm={data.storm} />}

      <div className="status-line">
        <div>
          <h1>{countLine(todo.length)}</h1>
          <p className="sub">{headline(f, toRain)}{f.heavy && toRain != null && toRain > 0 && <> · {t('safe cleaning window')} {duration(toRain)}</>}</p>
        </div>
        {plan && <Link className="btn primary" to="/run">{plural(plan.stops.length, 'See the run ({n} stop)', 'See the run ({n} stops)')}</Link>}
      </div>

      {data.basins.length === 0 ? (
        <section className="card">
          <h2>{t('No monitored basin yet')}</h2>
          <p className="sub">{t('Add a basin under Basins, then start a bridge with an upload key so its sensor sends readings here. To see the product with data, switch Data to Pitch demo in the menu.')}</p>
        </section>
      ) : <>
        <div className="map-layout">
          <BasinList rows={data.basins} selected={selected} onSelect={id => setSelected(id === selected ? null : id)} />
          <section className="card flush map-card-wrap" aria-label={t('Map')}>
            <BasinMap points={data.basins} line={plan?.line || sent?.line} stops={stops} depot={plan?.depot || sent?.depot}
              others={showCity ? city : []} selected={selected} onSelect={id => setSelected(id === selected ? null : id)} />
            {picked && <MapCard row={picked} onClose={() => setSelected(null)} />}
            <label className="check" style={{ padding: '10px 14px', borderTop: '1px solid var(--hairline)' }}>
              <input type="checkbox" checked={showCity} onChange={e => setShowCity(e.target.checked)} />{t("Show the city's other catch basins in this view (no sensor yet)")}
            </label>
          </section>
        </div>

        <div className="lifecycle" aria-label={t('Issue tracking')}>
          <span className="eyebrow">{t('Issue tracking')}</span>
          <span><b>{todo.filter(b => !b.dispatched).length}</b> {t('detected, no crew yet')}</span>
          <span aria-hidden="true">→</span>
          <span><b>{todo.filter(b => b.dispatched).length}</b> {t('crew dispatched')}</span>
          <span aria-hidden="true">→</span>
          <span><b>{confirmed}</b> {t('cleanings confirmed by the sensor (30 days)')}</span>
        </div>

        <div className="split" style={{ alignItems: 'stretch' }}>
          <div style={{ flex: '1 1 300px', maxWidth: 380, display: 'flex' }}><RunSummary run={data.run} /></div>
          <section className="card hero" aria-label={t('Storm timeline')} style={{ flex: '999 1 480px', minWidth: 0 }}>
            <div className="eyebrow">{t('Next 36 hours · Environment Canada GEM')}</div>
            <p className="sub" style={{ margin: 0 }}><span className={`chip ${data.season.risk ? 'inspect' : 'plain'}`}>{t(data.season.risk ? 'High-risk season' : 'Season')}</span> {seasonLine(data.season)}</p>
            {f.hours.length > 0 && <div className="chart-scroll"><StormTimeline rain={f.hours} nowIso={data.now} minutesToRain={f.heavy ? toRain : null}
              run={plan ? { from: fromNow(data.now, plan.leave), to: fromNow(data.now, plan.leave) + plan.drive_min + plan.service_min, label: t('Run · {from}–{to}', { from: plan.leave, to: plan.back }) } : undefined} /></div>}
          </section>
        </div>

        {data.checks.length > 0 && <Checks checks={data.checks} />}
      </>}
    </>
  )
}
