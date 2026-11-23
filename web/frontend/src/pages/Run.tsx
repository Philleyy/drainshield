import { useState } from 'react'
import { Link } from 'react-router-dom'
import BasinMap from '../components/BasinMap'
import { chipClass, priorityText } from '../components/BasinTable'
import { isEmergency, ListButton, spareText, StopList, useSendRun, type RunState } from '../components/Run'
import { num, t } from '../i18n'
import { clock, useData } from '../view'
import type { OverviewData } from './Overview'

/** Build the run: untick stops, choose when the truck leaves, check it fits before the rain, send it. */
export default function Run() {
  const [exclude, setExclude] = useState<string[]>([])
  const [leave, setLeave] = useState('')
  const { data: o, error } = useData<OverviewData>('/overview')
  const { data: run } = useData<RunState>('/run', { exclude: exclude.join(','), ...(leave ? { leave } : {}) })
  const { send, busy, error: sendError } = useSendRun()
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!o || !run) return <p className="muted">{t('Loading…')}</p>

  const candidates = o.basins.filter(b => b.category !== 'Normal' && !b.dispatched)
  const sectorNames = [...new Set(candidates.map(b => b.sector))]
  const p = run.suggested
  const late = p?.spare_min != null && p.spare_min < 0
  let fitText = t('No rain in the forecast.')
  if (p?.spare_min != null) fitText = late ? t('Does not fit before the rain.') : t('Fits before the rain.')
  const toggle = (id: string) => setExclude(x => (x.includes(id) ? x.filter(i => i !== id) : [...x, id]))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{p && isEmergency(p) ? t('Emergency dispatch') : t('Pre-storm run')} {candidates.length > 0 && <span className="chip inspect" style={{ verticalAlign: 'middle' }}>{t('Draft')}</span>}</h1>
          <p className="sub">{t('Every flagged basin that no crew has been sent to yet, urgent ones first, in the order that takes the least driving.')}</p>
        </div>
        {p && <div className="row no-print">
          {p.google[0] && <a className="btn" href={p.google[0]} target="_blank" rel="noreferrer">{t('Open in Google Maps')}</a>}
          <ListButton />
          <button type="button" className="btn primary" disabled={busy} onClick={async () => { if (await send(exclude, leave || null)) setExclude([]) }}>{t('Send to crew')}</button>
        </div>}
      </div>
      {sendError && <div className="notice error" role="alert">{sendError}</div>}

      {candidates.length === 0 && (
        <section className="card">
          <h2>{t('Nothing to send')}</h2>
          <p className="sub">{run.sent
            ? <>{t('The run sent at {time} covers every flagged basin: {done} of {n} stops done.', { time: clock(run.sent.sent), done: run.sent.done, n: run.sent.stops.length })} <Link to="/crew">{t('Open the crew view')}</Link> · <Link to="/run/list">{t('Cleaning list')}</Link></>
            : t('No basin is flagged and every sensor is reporting.')}</p>
        </section>
      )}

      {p && <div className={`notice ${late ? 'warn' : 'ok'}`}>
        <b>{fitText}</b>{' '}
        {t('Leaves {leave}, back at the yard {back} ({spare})', { leave: p.leave, back: p.back, spare: spareText(p) })} · {t('{n} stops', { n: p.stops.length })} · {p.drive_min} min {t('driving')} · {p.service_min} min {t('on site')} · {num(p.km)} km
        {p.note && <><br />{p.note}</>}
      </div>}

      {candidates.length > 0 && <div className="split">
        <div className="no-print" style={{ flex: '1 1 320px', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <section className="card" aria-label={t('Settings')}>
            <div className="field">
              <label htmlFor="leave">{t('Truck leaves the yard at')}</label>
              <input id="leave" type="time" value={leave || p?.leave || ''} onChange={e => setLeave(e.target.value)} />
              <span className="hint">{t('Default: the next quarter hour.')}</span>
            </div>
          </section>
          <section className="card flush" aria-label={t('Basins in this run')}>
            <div className="card-head"><h2>{t('Basins in this run')}</h2></div>
            {sectorNames.map(name => (
              <fieldset key={name} className="sector">
                <legend>{name}</legend>
                {candidates.filter(b => b.sector === name).map(b => (
                  <label key={b.id} className="check" style={{ alignItems: 'flex-start' }}>
                    <input type="checkbox" checked={!exclude.includes(b.id)} onChange={() => toggle(b.id)} />
                    <span><b>{b.id}</b> · {b.action}<small><span className={`chip ${chipClass(b.category)}`}>{priorityText(b.priority)}</span></small></span>
                  </label>
                ))}
              </fieldset>
            ))}
          </section>
        </div>
        <div style={{ flex: '999 1 480px', minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14 }}>
          {p ? <>
            <section className="card flush" aria-label={t('Route map')}><BasinMap points={o.basins} line={p.line} stops={p.stops} depot={p.depot} /></section>
            <section className="card" aria-label={t('Crew sheet')}><h2 style={{ marginBottom: 10 }}>{t('Crew sheet')}</h2><StopList stops={p.stops} /></section>
          </> : <section className="card"><p className="sub">{t('Tick at least one basin.')}</p></section>}
        </div>
      </div>}
    </>
  )
}
