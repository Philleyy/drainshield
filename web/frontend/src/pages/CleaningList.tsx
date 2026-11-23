import { Link } from 'react-router-dom'
import { downloadTable } from '../export'
import { colon, locale, num, plural, t } from '../i18n'
import { priorityText } from '../components/BasinTable'
import { spareText } from '../components/Run'
import { clock, useData } from '../view'
import type { OverviewData } from './Overview'

/** The run as a sheet for the crew or the contractor: print it (or save as PDF), or open it in Excel.
 *  Paid per job or by the hour, a shorter, ordered list is what saves money. */
export default function CleaningList() {
  const { data, error } = useData<OverviewData>('/overview')
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">{t('Loading…')}</p>

  const plan = data.run.suggested, sent = data.run.sent
  const stops = plan ? plan.stops.map(s => ({ ...s, label: priorityText(s.priority) }))
    : sent ? sent.stops.map(s => ({ ...s, label: '' })) : []
  const date = new Date(data.now).toLocaleDateString(locale, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })
  const f = data.forecast
  const rain = !f.available ? t('Forecast unavailable right now')
    : f.total_mm! < 0.5 ? t('No significant rain in the next 12 hours')
    : t('{mm} mm expected, up to {max} mm/h, starting {time}', { mm: Math.round(f.total_mm!), max: Math.round(f.max_mm_h!), time: f.starts ? clock(f.starts) : '—' })
  const header = [t('Stop'), t('Basin'), t('Address'), t('Sector'), t('What to do'), t('Expected arrival'), t('Done'), t('Notes')]
  const rows = stops.map(s => [s.stop, s.id, s.address, s.sector, s.label ? `${colon(s.label)} ${s.task}` : s.task, s.arrive, '', ''])

  return (
    <>
      <div className="page-head no-print">
        <div>
          <div className="sub"><Link to="/run">{t('Pre-storm run')}</Link> / {t('Cleaning list')}</div>
          <h1>{t('Cleaning list')}</h1>
          <p className="sub">{t('Ready to hand to the crew or the contractor: print it, save it as a PDF, or open it in Excel.')}</p>
        </div>
        {stops.length > 0 && <div className="row">
          <button type="button" className="btn primary" onClick={() => window.print()}>{t('Print / save as PDF')}</button>
          <button type="button" className="btn" onClick={() => downloadTable(`${t('cleaning-list')}-${data.now.slice(0, 10)}.csv`, header, rows)}>{t('Download for Excel')}</button>
        </div>}
      </div>

      {stops.length === 0 ? (
        <section className="card"><h2>{t('Nothing to clean')}</h2><p className="sub">{t('No basin is flagged and every sensor is reporting.')}</p></section>
      ) : (
        <article className="card sheet" aria-label={t('Cleaning list')}>
          <header className="sheet-head">
            <div>
              <h2>{t('Catch-basin cleaning list')}</h2>
              <p className="sub">{t('Dorval · Public Works')} · {date}</p>
            </div>
            <dl className="facts">
              <dt>{t('Forecast')}</dt><dd>{rain}</dd>
              {plan && <><dt>{t('Truck')}</dt><dd>{t('Leaves {leave}, back {back} ({spare})', { leave: plan.leave, back: plan.back, spare: spareText(plan) })}</dd>
                <dt>{t('Total')}</dt><dd>{plural(plan.stops.length, '{n} stop', '{n} stops')} · {plan.drive_min} min {t('driving')} · {plan.service_min} min {t('on site')} · {num(plan.km)} km</dd></>}
              {!plan && sent && <><dt>{t('Sent')}</dt><dd>{clock(sent.sent)} · {t('{done} of {n} stops done', { done: sent.done, n: sent.stops.length })}</dd></>}
            </dl>
          </header>
          <div className="table-wrap">
            <table className="sheet-table">
              <thead><tr>{header.map(h => <th key={h}>{h}</th>)}</tr></thead>
              <tbody>
                {stops.map(s => (
                  <tr key={s.id}>
                    <td><b>{s.stop}</b></td><td><b>{s.id}</b></td><td>{s.address}</td><td>{s.sector}</td>
                    <td>{s.label && <b>{colon(s.label)} </b>}{s.task}</td><td>{s.arrive}</td>
                    <td><span className="box" aria-hidden="true" /></td><td className="notes-cell" />
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="sub">{t('For each basin, tick Done or write why it could not be cleaned. The sensor confirms the work for the City: it sees the sump emptied, then the next rain shows whether the basin drains normally again.')}</p>
        </article>
      )}
    </>
  )
}
