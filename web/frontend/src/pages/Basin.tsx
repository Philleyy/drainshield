import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { chipClass, type Step } from '../components/BasinTable'
import { CrossSection, DayChart, type Dims, type RainBar } from '../components/Charts'
import { clock, day, useData, useView } from '../view'

interface Data {
  now: string; id: string; address: string; sector: string; facts: string; calibrating: string | null; category: string
  sensor: { online: boolean; iced: boolean; battery_pct: number | null; updated: string; mode: string | null }
  banner: { kind: string; head: string; rows: [string, string][]; confidence: string | null }
  steps: Step[] | null
  water: { key: string; title: string; text: string }
  drainage: { key: string; title: string; text: string; action: string }
  dims: Dims; invert_estimated: boolean; level_cm: number | null; sediment_pct: number | null; restriction: string | null
  levels: { t: string; cm: number }[]; rain: RainBar[]
  storms: { start: string; mm: number; verdict: string; status: string }[]
  log: { at: string; action: string; note: string }[]
}
const tone = (key: string) => ({ urgent: 'var(--urgent-text)', backing_up: 'var(--urgent-text)', clean_soon: 'var(--inspect-text)', high: 'var(--inspect-text)', watch: 'var(--inspect-text)', rising: 'var(--inspect-text)', no_data: 'var(--offline-text)' }[key] || 'var(--normal-text)')
// Only exceptions: a normal cleaning is detected by the sensor, nobody has to tap "cleaned".
const ACTIONS: [string, string][] = [['Inspected', 'Inspected'], ['Obstruction found', 'Obstruction found'], ['Requires further investigation', "Couldn't clean"],
  ['No issue found', 'No issue found'], ['Cleaned / vacuumed', "Cleaned (sensor can't confirm)"]]

export default function Basin() {
  const { id = '' } = useParams()
  const { data: d, error } = useData<Data>(`/basins/${encodeURIComponent(id)}`)
  const { url, refresh } = useView()
  const [note, setNote] = useState('')
  if (error) return <div className="notice error" role="alert">{error} <Link to="/basins">Back to the basins</Link></div>
  if (!d) return <p className="muted">Loading…</p>
  const calm = d.category === 'Normal'

  async function log(action: string, label: string) {
    try { await api(url(`/basins/${encodeURIComponent(id)}/log`), { body: { action } }); setNote(`Logged: ${label}`); refresh() } catch (e) {
      setNote(e instanceof ApiError ? e.message : 'Could not save.')
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <div className="sub"><Link to="/basins">Basins</Link> / {d.id}</div>
          <h1>Catch basin {d.id}</h1>
          <p className="sub">{d.address && `${d.address} · `}{d.facts}</p>
        </div>
        <span className={`chip ${d.sensor.online ? 'normal' : 'offline'}`}>
          Sensor {d.sensor.iced ? 'iced' : d.sensor.online ? 'online' : 'offline'}{d.sensor.battery_pct != null && ` · ${d.sensor.battery_pct}% battery`} · {d.sensor.updated}
        </span>
      </div>
      {d.calibrating && <div className="notice">Learning this basin's resting water level: {d.calibrating}</div>}

      <section className="card split" aria-label="What to do" style={{ borderColor: calm ? undefined : tone(d.banner.kind) }}>
        <div style={{ flex: '1 1 420px' }}>
          <span className={`chip ${chipClass(d.category)}`}>{d.category}</span>
          <h2 style={{ fontSize: 20, margin: '8px 0 12px' }}>{d.banner.head}</h2>
          <dl className="facts">
            {d.banner.rows.map(([k, v]) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}{k === 'Likely cause' && d.banner.confidence && <span className="chip plain" style={{ marginLeft: 8 }}>{d.banner.confidence} confidence</span>}</dd></div>)}
          </dl>
        </div>
        {d.steps && (
          <ol className="steps" aria-label="Progress">
            {d.steps.map(s => <li key={s.label} className={s.done ? 'done' : ''}><span>{s.label}{s.at && <small> · {day(s.at)}, {clock(s.at)}</small>}</span></li>)}
          </ol>
        )}
      </section>

      <div className="split">
        <section className="card" aria-label="Cross-section" style={{ flex: '999 1 440px', minWidth: 0 }}>
          <h2 style={{ marginBottom: 6 }}>Cross-section, to scale</h2>
          <CrossSection d={d.dims} levelCm={d.level_cm} sedimentPct={d.sediment_pct} restriction={d.restriction} estimated={d.invert_estimated} />
          <p className="sub">The sensor only sees the water surface. Sediment and restrictions are estimated from how the basin drains after rain.</p>
        </section>
        <div style={{ flex: '1 1 280px', display: 'flex', flexDirection: 'column', gap: 14 }}>
          <section className="card" aria-label="Water level now">
            <div className="eyebrow">Water level now</div>
            <div className="big" style={{ color: tone(d.water.key) }}>{d.water.title}</div>
            <p className="sub">{d.water.text}</p>
          </section>
          <section className="card" aria-label="Drainage performance">
            <div className="eyebrow">Drainage performance</div>
            <div className="big" style={{ color: tone(d.drainage.key) }}>{d.drainage.title}</div>
            <p className="sub">{d.drainage.text}{d.drainage.action && d.drainage.action !== 'No action' && ` · ${d.drainage.action}`}</p>
          </section>
          {d.sensor.mode && <section className="card" aria-label="Reading frequency">
            <div className="eyebrow">Reading mode</div>
            <div className="big">{d.sensor.mode}</div>
            <p className="sub">{{ DRY: 'One reading every 30 min to save battery', WATCH: 'Every 5 min: rain is forecast', STORM: 'Every 60 s: water is moving' }[d.sensor.mode] || ''}</p>
          </section>}
        </div>
      </div>

      <section className="card" aria-label="Rain and water level today">
        <h2 style={{ marginBottom: 8 }}>Rain and water level · today until {clock(d.now)}</h2>
        {d.levels.length ? <DayChart rain={d.rain} levels={d.levels} nowIso={d.now} /> : <p className="sub">No reading received today.</p>}
      </section>

      <div className="split">
        <section className="card flush" aria-label="Storm history" style={{ flex: '999 1 420px', minWidth: 0 }}>
          <div className="card-head"><h2>Past storms</h2></div>
          <div className="table-wrap"><table>
            <thead><tr><th>Storm</th><th>Rain</th><th>How it drained</th></tr></thead>
            <tbody>
              {d.storms.length === 0 && <tr><td colSpan={3} className="muted">No storm recorded yet.</td></tr>}
              {d.storms.map(h => (
                <tr key={h.start}><td style={{ whiteSpace: 'nowrap' }}>{day(h.start)}, {clock(h.start)}</td><td style={{ whiteSpace: 'nowrap' }}>{Math.round(h.mm)} mm</td>
                  <td style={{ color: h.status === 'ok' ? undefined : 'var(--inspect-text)', fontWeight: h.status === 'ok' ? 400 : 600 }}>{h.verdict || h.status}</td></tr>
              ))}
            </tbody>
          </table></div>
        </section>
        <section className="card flush" aria-label="Maintenance log" style={{ flex: '1 1 340px', minWidth: 0 }}>
          <div className="card-head"><h2>Maintenance log</h2></div>
          <div className="table-wrap"><table>
            <tbody>
              {d.log.length === 0 && <tr><td className="muted">Nothing logged yet.</td></tr>}
              {d.log.map(l => <tr key={l.at + l.action}><td style={{ whiteSpace: 'nowrap' }}>{day(l.at)}, {clock(l.at)}</td><td>{l.action}{l.note && <small>{l.note}</small>}</td></tr>)}
            </tbody>
          </table></div>
          <div className="log-actions no-print">
            <span className="label">Log an exception</span>
            <div className="row">{ACTIONS.map(([action, label]) => <button key={action} type="button" className="btn small" onClick={() => log(action, label)}>{label}</button>)}</div>
            {note && <p className="sub" role="status">{note}</p>}
          </div>
        </section>
      </div>
    </>
  )
}
