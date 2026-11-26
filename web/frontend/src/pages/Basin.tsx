import { useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { CATEGORY_LABEL, chipClass, type Check, type Step } from '../components/BasinTable'
import { t } from '../i18n'
import { checkText } from './Overview'
import BasinMap from '../components/BasinMap'
import { CrossSection, DayChart, type Dims, type RainBar } from '../components/Charts'
import { clock, day, useData, useView } from '../view'

interface Data {
  now: string; id: string; address: string; sector: string; lat: number; lon: number; facts: string; calibrating: string | null; category: string
  sensor: { online: boolean; iced: boolean; battery_pct: number | null; updated: string; mode: string | null; mode_code: string | null }
  banner: { kind: string; head: string; rows: [string, string][]; confidence: string | null }
  steps: Step[] | null; check: Check | null
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
const MODE: Record<string, string> = { DRY: 'One reading every 30 min to save battery', WATCH: 'Every 5 min: rain is forecast', STORM: 'Every 60 s: water is moving' }

type Item = { at: string; kind: 'storm' | 'crew' | 'done' | 'problem' | 'sensor'; title: string; note: string; bad?: boolean }
const kindOf = (action: string): Item['kind'] => {
  const a = action.toLowerCase()
  if (/dispatch|envoy/.test(a)) return 'crew'
  if (/clean|nettoy|vidang|no issue|aucun problème|inspect/.test(a)) return 'done'
  if (/obstruct|investig|impossible/.test(a)) return 'problem'
  return 'sensor'
}

/** Storms and maintenance in one timeline, newest first: what happened to this basin, at a glance. */
function Activity({ log, storms, children }: { log: Data['log']; storms: Data['storms']; children: ReactNode }) {
  const [all, setAll] = useState(false)
  const items: Item[] = [
    ...log.map(l => ({ at: l.at, kind: kindOf(l.action), title: l.action, note: l.note })),
    ...storms.map(s => ({ at: s.start, kind: 'storm' as const, title: t('Rain of {mm} mm', { mm: Math.round(s.mm) }), note: s.verdict || '', bad: s.status !== 'ok' })),
  ].sort((a, b) => b.at.localeCompare(a.at))
  const shown = all ? items : items.slice(0, 8)
  return (
    <section className="card flush" aria-label={t('Activity')}>
      <div className="card-head"><h2>{t('Activity')}</h2></div>
      {items.length === 0 && <p className="sub" style={{ padding: '4px 16px' }}>{t('Nothing logged yet.')}</p>}
      <ol className="timeline">
        {shown.map(it => (
          <li key={it.at + it.title} className={`tl-${it.kind}`}>
            <span className="tl-dot" aria-hidden="true" />
            <div><b>{it.title}</b>{it.note && <small style={it.bad ? { color: 'var(--inspect-text)', fontWeight: 600 } : undefined}>{it.note}</small>}</div>
            <time>{day(it.at)}, {clock(it.at)}</time>
          </li>
        ))}
      </ol>
      {items.length > 8 && <div style={{ padding: '0 16px 12px' }}><button type="button" className="btn small" onClick={() => setAll(!all)}>{all ? t('Show less') : t('Show all ({n})', { n: items.length })}</button></div>}
      {children}
    </section>
  )
}

export default function Basin() {
  const { id = '' } = useParams()
  const { data: d, error } = useData<Data>(`/basins/${encodeURIComponent(id)}`)
  const { url, refresh } = useView()
  const { user } = useAuth()
  const navigate = useNavigate()
  const mayRemove = user?.role === 'admin' || user?.role === 'engineering'
  async function remove() {
    if (!window.confirm(t('Remove basin {id}? Its settings and maintenance log are deleted for good.', { id }))) return
    try { await api(`/basins/${encodeURIComponent(id)}`, { method: 'DELETE' }); navigate('/basins') }
    catch (e) { window.alert(e instanceof ApiError ? e.message : t('Could not remove it.')) }
  }
  const [note, setNote] = useState('')
  if (error) return <div className="notice error" role="alert">{error} <Link to="/basins">{t('Back to the basins')}</Link></div>
  if (!d) return <p className="muted">{t('Loading…')}</p>
  const calm = d.category === 'Normal'

  async function log(action: string, label: string) {
    try { await api(url(`/basins/${encodeURIComponent(id)}/log`), { body: { action } }); setNote(t('Logged: {what}', { what: t(label) })); refresh() } catch (e) {
      setNote(e instanceof ApiError ? e.message : t('Could not save.'))
    }
  }

  const storm = d.storms[0]
  return (
    <>
      <div className="page-head">
        <div>
          <div className="sub"><Link to="/basins">{t('Basins')}</Link> / {d.id}</div>
          <h1>{t('Catch basin {id}', { id: d.id })}</h1>
          <p className="sub">{d.address && `${d.address} · `}{d.facts}</p>
        </div>
        <span className={`chip ${d.sensor.online ? 'normal' : 'offline'}`}>
          {t(d.sensor.iced ? 'Sensor iced' : d.sensor.online ? 'Sensor online' : 'Sensor offline')}{d.sensor.battery_pct != null && ` · ${t('{pct}% battery', { pct: d.sensor.battery_pct })}`} · {d.sensor.updated}
        </span>
      </div>

      <div className="profile">
        <aside className="profile-side">
          <section className="card flush" aria-label={t('Map')}>
            <BasinMap points={[{ id: d.id, lat: d.lat, lon: d.lon, category: d.category }]} height="220px" legend={false} />
            <dl className="facts profile-facts">
              <dt>{t('Address')}</dt><dd>{d.address || '—'}</dd>
              <dt>{t('Sector')}</dt><dd>{d.sector || '—'}</dd>
              <dt>{t('Basin')}</dt><dd>{d.facts}</dd>
              <dt>{t('Sensor')}</dt><dd>{t(d.sensor.iced ? 'Sensor iced' : d.sensor.online ? 'Sensor online' : 'Sensor offline')}{d.sensor.battery_pct != null && ` · ${t('{pct}% battery', { pct: d.sensor.battery_pct })}`}<small>{d.sensor.updated}</small></dd>
              {d.sensor.mode && <><dt>{t('Reading mode')}</dt><dd>{d.sensor.mode}{d.sensor.mode_code && MODE[d.sensor.mode_code] && <small>{t(MODE[d.sensor.mode_code])}</small>}</dd></>}
            </dl>
          </section>
          {mayRemove && <section className="card danger-zone no-print" aria-label={t('Remove this basin')}>
            <div>
              <h2>{t('Remove this basin')}</h2>
              <p className="sub">{t('Deletes its as-built settings and maintenance log. Its sensor readings stay on the Sensors page until you remove the sensor too.')}</p>
            </div>
            <button type="button" className="btn danger" onClick={remove}>{t('Remove basin')}</button>
          </section>}
        </aside>

        <div className="profile-main">
          <section className="card split" aria-label={t('What to do')} style={{ borderColor: calm ? undefined : tone(d.banner.kind) }}>
            <div style={{ flex: '1 1 380px' }}>
              <span className={`chip ${chipClass(d.category)}`}>{CATEGORY_LABEL[d.category] || d.category}</span>
              <h2 style={{ fontSize: 20, margin: '8px 0 12px' }}>{d.banner.head}</h2>
              <dl className="facts">
                {d.banner.rows.map(([k, v], i) => <div key={k} style={{ display: 'contents' }}><dt>{k}</dt><dd>{v}{i === 1 && d.banner.confidence && <span className="chip plain" style={{ marginLeft: 8 }}>{t('Confidence: {level}', { level: d.banner.confidence })}</span>}</dd></div>)}
              </dl>
            </div>
            {d.steps && (
              <ol className="steps" aria-label={t('Progress')}>
                {d.steps.map(s => <li key={s.label} className={s.done ? 'done' : ''}><span>{s.label}{s.at && <small> · {day(s.at)}, {clock(s.at)}</small>}</span></li>)}
              </ol>
            )}
          </section>

          {d.calibrating && <div className="notice">{t("Learning this basin's resting water level: {note}", { note: d.calibrating })}</div>}
          {d.check && <div className={`notice ${d.check.state === 'confirmed' ? 'ok' : d.check.state === 'still_slow' ? 'warn' : ''}`}>
            <b>{checkText(d.check)}</b> · {t('cleaned {when}', { when: `${day(d.check.cleaned_at)}, ${clock(d.check.cleaned_at)}` })}
            {' · '}{d.check.rain_at ? t('judged on the rain of {when}', { when: `${day(d.check.rain_at)}, ${clock(d.check.rain_at)}` }) : t('the next rain big enough will tell whether it drains normally again')}
          </div>}

          <div className="split" style={{ alignItems: 'stretch' }}>
            <section className="card" aria-label={t('Cross-section')} style={{ flex: '999 1 400px', minWidth: 0 }}>
              <h2 style={{ marginBottom: 6 }}>{t('Cross-section, to scale')}</h2>
              <CrossSection d={d.dims} levelCm={d.level_cm} sedimentPct={d.sediment_pct} restriction={d.restriction} estimated={d.invert_estimated} />
              <p className="sub">{t('The sensor only sees the water surface. Sediment and restrictions are estimated from how the basin drains after rain.')}</p>
            </section>
            <div className="metrics">
              <section className="card" aria-label={t('Water level now')}>
                <div className="eyebrow">{t('Water level now')}</div>
                <div className="big" style={{ color: tone(d.water.key) }}>{d.water.title}</div>
                <p className="sub">{d.water.text}</p>
              </section>
              <section className="card" aria-label={t('Drainage performance')}>
                <div className="eyebrow">{t('Drainage performance')}</div>
                <div className="big" style={{ color: tone(d.drainage.key) }}>{d.drainage.title}</div>
                <p className="sub">{d.drainage.text}{d.drainage.action && d.drainage.action !== t('No action') && ` · ${d.drainage.action}`}</p>
              </section>
              <section className="card" aria-label={t('Last storm')}>
                <div className="eyebrow">{t('Last storm')}</div>
                <div className="big">{storm ? `${Math.round(storm.mm)} mm` : '—'}</div>
                <p className="sub">{storm ? `${day(storm.start)} · ${storm.verdict || storm.status}` : t('No storm recorded yet.')}</p>
              </section>
            </div>
          </div>

          <section className="card" aria-label={t('Rain and water level today')}>
            <h2 style={{ marginBottom: 8 }}>{t('Rain and water level · today until {time}', { time: clock(d.now) })}</h2>
            {d.levels.length ? <DayChart rain={d.rain} levels={d.levels} nowIso={d.now} /> : <p className="sub">{t('No reading received today.')}</p>}
          </section>

          <Activity log={d.log} storms={d.storms}>
            <div className="log-actions no-print">
              <span className="label">{t('Log an exception')}</span>
              <div className="row">{ACTIONS.map(([action, label]) => <button key={action} type="button" className="btn small" onClick={() => log(action, label)}>{t(label)}</button>)}</div>
              {note && <p className="sub" role="status">{note}</p>}
            </div>
          </Activity>
        </div>
      </div>
    </>
  )
}
