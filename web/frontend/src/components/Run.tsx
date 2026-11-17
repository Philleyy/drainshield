// The pre-storm run: its data shapes, and the summary card shown on the overview.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { clock, duration, useView } from '../view'
import { chipClass } from './BasinTable'

export interface PlanStop { stop: number; id: string; address: string; sector: string; category: string; priority: string; task: string; arrive: string; depart: string; service_min: number; lat: number; lon: number }
export interface Plan { stops: PlanStop[]; leave: string; back: string; drive_min: number; service_min: number; km: number; source: string; note: string; line: number[][]; google: string[]; depot: number[]; rain_starts: string | null; spare_min: number | null }
export interface SentStop { stop: number; id: string; address: string; sector: string; category: string; task: string; arrive: string; done: boolean; done_text: string; lat: number; lon: number }
export interface Sent { sent: string; stops: SentStop[]; done: number; line: number[][]; depot: number[] }
export interface RunState { suggested: Plan | null; sent: Sent | null }

export const isEmergency = (p: Plan) => p.stops.some(s => s.priority.startsWith('Flooding'))
export const sectors = (stops: { sector: string }[]) => new Set(stops.map(s => s.sector)).size
export function spareText(p: Plan) {
  if (p.spare_min == null) return 'no rain in the forecast'
  return p.spare_min >= 0 ? `${duration(p.spare_min)} before the rain` : `${duration(-p.spare_min)} after the rain starts`
}

/** Sends the suggested run: one "Crew dispatched" entry per stop, which is what the crew view reads. */
export function useSendRun() {
  const { url, refresh } = useView()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function send(exclude: string[] = [], leave: string | null = null) {
    setBusy(true); setError('')
    try { await api(url('/run/send'), { body: { exclude, leave } }); refresh(); return true } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send the run.'); return false
    } finally { setBusy(false) }
  }
  return { send, busy, error }
}

export function StopList({ stops }: { stops: (PlanStop | SentStop)[] }) {
  return (
    <ol className="stops">
      {stops.map(s => {
        const done = 'done' in s && s.done
        return (
          <li key={s.id}>
            <span className={`num ${done ? 'done' : chipClass(s.category)}`}>{done ? '✓' : s.stop}</span>
            <div><Link to={`/basins/${s.id}`}><b>{s.id}</b></Link> · {s.address}
              <small>{done && 'done_text' in s ? s.done_text : s.task}</small></div>
            <span className="muted">{s.arrive}</span>
          </li>
        )
      })}
    </ol>
  )
}

export default function RunSummary({ run }: { run: RunState }) {
  const { send, busy, error } = useSendRun()
  const p = run.suggested
  if (p) {
    return (
      <section className="card run suggested" aria-label="Suggested run">
        <div>
          <div className="eyebrow" style={{ color: 'var(--window)' }}>{isEmergency(p) ? 'Emergency dispatch' : 'Suggested pre-storm run'}</div>
          <h2 className="run-title">{p.stops.length} {p.stops.length === 1 ? 'stop' : 'stops'} in {sectors(p.stops)} {sectors(p.stops) === 1 ? 'sector' : 'sectors'}</h2>
        </div>
        <div className="run-stats">
          <div><b>{p.drive_min} min</b><small>driving</small></div>
          <div><b>{p.service_min} min</b><small>on site</small></div>
          <div><b>{p.back}</b><small>back, {spareText(p)}</small></div>
        </div>
        <StopList stops={p.stops} />
        {error && <div className="notice error" role="alert">{error}</div>}
        <div className="row" style={{ marginTop: 'auto' }}>
          <button type="button" className="btn primary" style={{ flex: '2 1 160px' }} disabled={busy} onClick={() => send()}>Send to crew</button>
          <Link to="/run" className="btn" style={{ flex: '1 1 100px' }}>Adjust</Link>
        </div>
        {run.sent && <p className="sub">An earlier run was sent at {clock(run.sent.sent)}: {run.sent.done} of {run.sent.stops.length} stops done. <Link to="/crew">Crew view</Link></p>}
      </section>
    )
  }
  if (run.sent) {
    const s = run.sent
    return (
      <section className="card run" aria-label="Run in progress">
        <div>
          <div className="eyebrow">Run sent at {clock(s.sent)}</div>
          <h2 className="run-title">{s.done} of {s.stops.length} stops done</h2>
        </div>
        <StopList stops={s.stops} />
        <p className="sub">Stops tick themselves off when the sensor sees the sump emptied, or the sensor reports again.</p>
        <Link to="/crew" className="btn" style={{ marginTop: 'auto' }}>Open the crew view</Link>
      </section>
    )
  }
  return (
    <section className="card run" aria-label="No run needed">
      <div className="eyebrow">Pre-storm run</div>
      <h2 className="run-title">No run needed</h2>
      <p className="sub">No basin is flagged and every sensor is reporting.</p>
    </section>
  )
}
