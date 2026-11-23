import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { accuracy, cityBasins, fit, type CityBasin } from '../city'
import BasinList, { MapCard } from '../components/BasinList'
import BasinMap from '../components/BasinMap'
import { locale, plural, t } from '../i18n'
import { useData, useView } from '../view'
import type { OverviewData } from './Overview'

const START = { basin_id: '', municipal_id: '', address: '', latitude: '', longitude: '', diameter_mm: '610', invert_depth_mm: '', outlet_mm: '250', sump_mm: '300', sensor_depth_mm: '400', has_trap: true }
const NUMBERS = ['latitude', 'longitude', 'diameter_mm', 'outlet_mm', 'sump_mm', 'sensor_depth_mm'] as const
const number = (v: string) => Number(v.replace(',', '.'))

/** Find the basin in the city's open-data list by its ID or address; picking one fills the position. */
function CitySearch({ picked, onPick }: { picked: CityBasin | null; onPick: (b: CityBasin) => void }) {
  const [all, setAll] = useState<CityBasin[] | null>(null)
  const [q, setQ] = useState('')
  useEffect(() => { cityBasins().then(setAll).catch(() => setAll([])) }, [])
  const words = q.trim().toLowerCase()
  const hits = !all || words.length < 2 ? [] : all.filter(b => b.id.startsWith(words) || b.address.toLowerCase().includes(words)).slice(0, 6)
  return (
    <div className="field">
      <label htmlFor="city-search">{t("Find it in the city's list (optional)")}</label>
      <input id="city-search" value={q} onChange={e => setQ(e.target.value)} placeholder={t('City basin ID or street, e.g. 7082692 or Mimosa')} autoComplete="off" />
      <span className="hint">{all == null ? t('Loading the city list…') : all.length ? t('{n} catch basins from the Ville de Montréal open data. Or click a grey dot on the map.', { n: all.length.toLocaleString(locale) }) : t('City list not available.')}</span>
      {hits.length > 0 && <div className="row">{hits.map(b => (
        <button key={b.id} type="button" className="btn small" onClick={() => { onPick(b); setQ('') }}>{b.id} · {b.address}</button>
      ))}</div>}
      {picked && <div className={`notice ${fit(picked.type).ok ? 'ok' : 'warn'}`}>
        <b>{t('City basin {id}', { id: picked.id })}</b> · {picked.address}<br />
        {fit(picked.type).text}{accuracy(picked.provenance) && ` · ${t('position')} ${accuracy(picked.provenance)}`}{picked.tier && ` · ${t('pilot priority')} ${picked.tier}`}
      </div>}
    </div>
  )
}

/** The as-built form: what a city knows from its plans (pipe depth and diameters), not catalogue part names. */
function AddBasin({ onSaved, cityId, onPreview }: { onSaved: () => void; cityId: string | null; onPreview: (p: { lat: number; lon: number } | null) => void }) {
  const [f, setF] = useState(START)
  const [picked, setPicked] = useState<CityBasin | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const pick = (b: CityBasin) => {
    setPicked(b)
    setF(old => ({ ...old, municipal_id: b.id, address: b.address, latitude: String(b.lat), longitude: String(b.lon), basin_id: old.basin_id || b.id }))
  }
  useEffect(() => {                                       // arrived from a grey dot on the map
    if (cityId) cityBasins().then(all => { const b = all.find(x => x.id === cityId); if (b) pick(b) }).catch(() => {})
  }, [cityId])
  useEffect(() => {                                       // the new basin's pin follows the position on the map
    const lat = number(f.latitude), lon = number(f.longitude)
    onPreview(lat >= 44.9 && lat <= 62.6 && lon >= -79.8 && lon <= -57.1 ? { lat, lon } : null)
  }, [f.latitude, f.longitude])   // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof typeof START) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const select = (k: keyof typeof START, label: string, options: [string, string][]) => (
    <div className="field"><label htmlFor={k}>{label}</label>
      <select id={k} value={String(f[k])} onChange={set(k)}>{options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
  )
  const input = (k: keyof typeof START, label: string, hint = '', numeric = true, required = true) => (
    <div className="field"><label htmlFor={k}>{label}</label>
      <input id={k} value={String(f[k])} onChange={set(k)} inputMode={numeric ? 'decimal' : undefined} required={required} />
      {hint && <span className="hint">{hint}</span>}</div>
  )
  async function submit(e: FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = { ...f, invert_depth_mm: f.invert_depth_mm.trim() ? number(f.invert_depth_mm) : null }
    for (const k of NUMBERS) body[k] = number(String(f[k]))
    if ([...NUMBERS.map(k => body[k]), body.invert_depth_mm ?? 0].some(v => !Number.isFinite(v as number))) {
      setMessage({ ok: false, text: t('Latitude, longitude and depths must be numbers.') }); return
    }
    try {
      const r = await api<{ warnings: string[] }>('/basins', { body })
      setMessage({ ok: true, text: t('Saved {id}. {warnings} Its readings appear here once a bridge uploads them under this ID (--basin {id}).', { id: f.basin_id, warnings: r.warnings.map(w => t(w)).join(' ') }) })
      setF(START); setPicked(null); onSaved()
    } catch (err) { setMessage({ ok: false, text: err instanceof ApiError ? err.message : t('Could not save.') }) }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0 0' }}>
      <CitySearch picked={picked} onPick={pick} />
      <div className="form-grid" style={{ alignItems: 'start' }}>
        {input('basin_id', t('Basin ID'), t('The same name the bridge uploads with, e.g. S4-A'), false)}
        {input('address', t('Address (optional)'), '', false, false)}
        {input('latitude', t('Latitude'), t('e.g. {v}', { v: '45.4468' }))}
        {input('longitude', t('Longitude'), t('e.g. {v}', { v: '-73.7513' }))}
        {input('sensor_depth_mm', t('Sensor depth from the grate (mm)'), t('Tape it when you mount the sensor'))}
        {input('invert_depth_mm', t('Outlet invert depth from the grate (mm, optional)'), t('Profondeur du radier, if the plans have it. Leave empty: the sensor learns it from the resting water in about 2 dry days'), true, false)}
        {select('diameter_mm', t('Basin internal diameter'), [['405', '405 mm'], ['610', t('610 mm (24" standard)')], ['915', '915 mm'], ['1220', '1220 mm']])}
        {select('outlet_mm', t('Outlet pipe diameter'), ['150', '200', '250', '300', '375', '450'].map(v => [v, `${v} mm`] as [string, string]))}
        {select('sump_mm', t('Sump depth (réserve)'), [['0', '0 mm'], ['300', t('300 mm (default)')], ['500', '500 mm']])}
      </div>
      <label className="check"><input type="checkbox" checked={f.has_trap} onChange={e => setF({ ...f, has_trap: e.target.checked })} />{t('Cast-iron trap (cloche) installed')}</label>
      {message && <div className={`notice ${message.ok ? 'ok' : 'error'}`} role={message.ok ? 'status' : 'alert'}>{message.text}</div>}
      <div><button type="submit" className="btn primary">{t('Save basin')}</button></div>
    </form>
  )
}

export default function Basins() {
  const { data, error } = useData<OverviewData>('/overview')
  const { demo, refresh } = useView()
  const { user } = useAuth()
  const [params, setParams] = useSearchParams()
  const cityId = params.get('city')
  const [adding, setAdding] = useState(!!cityId)
  const [selected, setSelected] = useState<string | null>(null)
  const [preview, setPreview] = useState<{ lat: number; lon: number } | null>(null)
  const [city, setCity] = useState<CityBasin[]>([])
  useEffect(() => { if (cityId) setAdding(true) }, [cityId])
  const mayAdd = !demo && (user?.role === 'admin' || user?.role === 'engineering')
  const form = mayAdd && (adding || data?.basins.length === 0)
  useEffect(() => { if (form) cityBasins().then(setCity).catch(() => setCity([])) }, [form])
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">{t('Loading…')}</p>
  const picked = data.basins.find(b => b.id === selected) || null
  const close = () => { setAdding(false); setPreview(null); setParams({}) }
  return (
    <>
      <div className="page-head">
        <div><h1>{t('Basins')}</h1><p className="sub">{plural(data.basins.length, '{n} monitored basin, most urgent first. Click one for its detail.', '{n} monitored basins, most urgent first. Click one for its detail.')}</p></div>
      </div>
      {demo && <p className="sub">{t('Basins are added in Live data. The pitch demo always shows the 12 scripted pilot basins.')}</p>}
      <div className="map-layout">
        {form ? (
          <aside className="card side-form" aria-label={t('Add a basin')}>
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <h2>{t('Add a basin')}</h2>
              {data.basins.length > 0 && <button type="button" className="btn small" onClick={close}>{t('Back to the list')}</button>}
            </div>
            <p className="sub">{t('Click a grey dot on the map or search the city list: the new basin appears on the map as you fill in its position. Saving again with the same ID updates it.')}</p>
            <AddBasin onSaved={refresh} cityId={cityId} onPreview={setPreview} />
          </aside>
        ) : (
          <BasinList rows={data.basins} selected={selected} onSelect={id => setSelected(id === selected ? null : id)}
            footer={mayAdd && <div style={{ padding: 12 }}><button type="button" className="btn" style={{ width: '100%' }} onClick={() => setAdding(true)}>+ {t('Add a basin')}</button></div>} />
        )}
        <section className="card flush map-card-wrap" aria-label={t('Map')}>
          <BasinMap points={data.basins} others={form ? city : []} selected={form ? null : selected} onSelect={id => setSelected(id === selected ? null : id)}
            onPickCity={id => setParams({ city: id })} preview={form ? preview : null} />
          {picked && !form && <MapCard row={picked} onClose={() => setSelected(null)} />}
        </section>
      </div>
    </>
  )
}
