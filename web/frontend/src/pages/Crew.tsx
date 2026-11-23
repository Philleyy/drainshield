import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { ListButton } from '../components/Run'
import { t } from '../i18n'
import { clock, duration, minutesBetween, useData, useView } from '../view'
import type { OverviewData } from './Overview'

/** The run as the truck crew sees it on a tablet: big targets, and nothing to tap when all goes well. */
export default function Crew() {
  const { data, error } = useData<OverviewData>('/overview')
  const { url, refresh } = useView()
  const [note, setNote] = useState('')
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">{t('Loading…')}</p>
  const run = data.run.sent
  if (!run) {
    return <section className="card"><h1>{t('No run today')}</h1><p className="sub">{t('When the dispatcher sends a run, its stops appear here.')} <Link to="/run">{t('Pre-storm run')}</Link></p></section>
  }
  const toRain = data.forecast.starts ? minutesBetween(data.now, data.forecast.starts) : null
  const current = run.stops.find(s => !s.done)

  async function log(id: string, action: string, text: string) {
    try { await api(url(`/basins/${id}/log`), { body: { action, note: text } }); setNote(t('Logged for {id}: {text}', { id, text: t(text) })); refresh() } catch (e) {
      setNote(e instanceof ApiError ? e.message : t('Could not save.'))
    }
  }

  return (
    <div className="crew">
      <header className="crew-head">
        <div><div className="sub" style={{ color: 'inherit', opacity: 0.8 }}>{t('Sent {sent} · now {now}', { sent: clock(run.sent), now: clock(data.now) })}</div><h1>{t('Pre-storm run')}</h1></div>
        {toRain != null && toRain > 0 && <div style={{ textAlign: 'right' }}><div className="big">{duration(toRain)}</div><div>{t('until the rain')}</div></div>}
      </header>
      <div className="card row">
        <b>{t('{done} of {n} done', { done: run.done, n: run.stops.length })}</b>
        <progress value={run.done} max={run.stops.length} style={{ flex: 1, height: 12 }} aria-label={t('Stops done')} />
        <ListButton className="btn small" />
      </div>
      {note && <div className="notice ok" role="status">{note}</div>}
      {run.stops.map(s => (
        <article key={s.id} className={`card stop ${s.done ? 'done' : s === current ? 'current' : ''}`}>
          <div className="row" style={{ flexWrap: 'nowrap', alignItems: 'flex-start' }}>
            <span className={`num big-num ${s.done ? 'done' : ''}`}>{s.done ? '✓' : s.stop}</span>
            <div style={{ flex: 1 }}>
              <h2><Link to={`/basins/${s.id}`}>{s.id}</Link> · {s.address}</h2>
              <p className="sub">{s.done ? s.done_text : `${t('Arrive about {time}', { time: s.arrive })} · ${s.task}`}</p>
              {!s.done && s === current && <>
                <p className="notice">{t('Watching the sensor: this stop ticks itself off when the sump is emptied (or the sensor reports again). Nothing to tap.')}</p>
                <div className="row">
                  <button type="button" className="btn tall" onClick={() => log(s.id, 'Requires further investigation', "Couldn't clean")}>{t("Couldn't clean")}</button>
                  <button type="button" className="btn tall" onClick={() => log(s.id, 'Obstruction found', 'Obstruction found by the crew')}>{t('Obstruction found')}</button>
                </div>
              </>}
            </div>
          </div>
        </article>
      ))}
    </div>
  )
}
