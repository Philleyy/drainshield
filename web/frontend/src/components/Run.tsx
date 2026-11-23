// The pre-storm run: its data shapes, and the summary card shown on the overview.
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { plural, t } from '../i18n'
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
  if (p.spare_min == null) return t('no rain in the forecast')
  return p.spare_min >= 0 ? t('{d} before the rain', { d: duration(p.spare_min) }) : t('{d} after the rain starts', { d: duration(-p.spare_min) })
}

/** Sends the suggested run: one "Crew dispatched" entry per stop, which is what the crew view reads. */
export function useSendRun() {
  const { url, refresh } = useView()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  async function send(exclude: string[] = [], leave: string | null = null) {
    setBusy(true); setError('')
    try { await api(url('/run/send'), { body: { exclude, leave } }); refresh(); return true } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Could not send the run.')); return false
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

/** One click from the run to a list the foreman can hand to the crew or the contractor. */
export function ListButton({ className = 'btn' }: { className?: string }) {
  return <Link to="/run/list" className={className}>{t('Cleaning list (PDF / Excel)')}</Link>
}

export default function RunSummary({ run }: { run: RunState }) {
  const { send, busy, error } = useSendRun()
  const p = run.suggested
  if (p) {
    const n = sectors(p.stops)
    return (
      <section className="card run suggested" aria-label={t('Suggested run')}>
        <div>
          <div className="eyebrow" style={{ color: 'var(--window)' }}>{isEmergency(p) ? t('Emergency dispatch') : t('Suggested pre-storm run')}</div>
          <h2 className="run-title">{plural(p.stops.length, '{n} stop', '{n} stops')} {plural(n, 'in {n} sector', 'in {n} sectors')}</h2>
        </div>
        <div className="run-stats">
          <div><b>{p.drive_min} min</b><small>{t('driving')}</small></div>
          <div><b>{p.service_min} min</b><small>{t('on site')}</small></div>
          <div><b>{p.back}</b><small>{t('back, {spare}', { spare: spareText(p) })}</small></div>
        </div>
        <StopList stops={p.stops} />
        {error && <div className="notice error" role="alert">{error}</div>}
        <div className="row" style={{ marginTop: 'auto' }}>
          <button type="button" className="btn primary" style={{ flex: '2 1 160px' }} disabled={busy} onClick={() => send()}>{t('Send to crew')}</button>
          <Link to="/run" className="btn" style={{ flex: '1 1 100px' }}>{t('Adjust')}</Link>
        </div>
        <ListButton />
        {run.sent && <p className="sub">{t('An earlier run was sent at {time}: {done} of {n} stops done.', { time: clock(run.sent.sent), done: run.sent.done, n: run.sent.stops.length })} <Link to="/crew">{t('Crew view')}</Link></p>}
      </section>
    )
  }
  if (run.sent) {
    const s = run.sent
    return (
      <section className="card run" aria-label={t('Run in progress')}>
        <div>
          <div className="eyebrow">{t('Run sent at {time}', { time: clock(s.sent) })}</div>
          <h2 className="run-title">{t('{done} of {n} stops done', { done: s.done, n: s.stops.length })}</h2>
        </div>
        <StopList stops={s.stops} />
        <p className="sub">{t('Stops tick themselves off when the sensor sees the sump emptied, or the sensor reports again.')}</p>
        <div className="row" style={{ marginTop: 'auto' }}>
          <Link to="/crew" className="btn" style={{ flex: '1 1 160px' }}>{t('Open the crew view')}</Link>
          <ListButton className="btn" />
        </div>
      </section>
    )
  }
  return (
    <section className="card run" aria-label={t('No run needed')}>
      <div className="eyebrow">{t('Pre-storm run')}</div>
      <h2 className="run-title">{t('No run needed')}</h2>
      <p className="sub">{t('No basin is flagged and every sensor is reporting.')}</p>
    </section>
  )
}
