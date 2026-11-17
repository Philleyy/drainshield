import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { accuracy, cityBasins, fit, type CityBasin } from '../city'
import BasinTable from '../components/BasinTable'
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
      <label htmlFor="city-search">Find it in the city's list (optional)</label>
      <input id="city-search" value={q} onChange={e => setQ(e.target.value)} placeholder="City basin ID or street, e.g. 7082692 or Mimosa" autoComplete="off" />
      <span className="hint">{all == null ? 'Loading the city list…' : all.length ? `${all.length.toLocaleString('en-CA')} catch basins from the Ville de Montréal open data. Or click a grey dot on the overview map.` : 'City list not available.'}</span>
      {hits.length > 0 && <div className="row">{hits.map(b => (
        <button key={b.id} type="button" className="btn small" onClick={() => { onPick(b); setQ('') }}>{b.id} · {b.address}</button>
      ))}</div>}
      {picked && <div className={`notice ${fit(picked.type).ok ? 'ok' : 'warn'}`}>
        <b>City basin {picked.id}</b> · {picked.address}<br />
        {fit(picked.type).text}{accuracy(picked.provenance) && ` · position ${accuracy(picked.provenance)}`}{picked.tier && ` · pilot priority ${picked.tier}`}
      </div>}
    </div>
  )
}

/** The as-built form: what a city knows from its plans (pipe depth and diameters), not catalogue part names. */
function AddBasin({ onSaved, cityId }: { onSaved: () => void; cityId: string | null }) {
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
      setMessage({ ok: false, text: 'Latitude, longitude and depths must be numbers.' }); return
    }
    try {
      const r = await api<{ warnings: string[] }>('/basins', { body })
      setMessage({ ok: true, text: `Saved ${f.basin_id}. ${r.warnings.join(' ')} Its readings appear here once a bridge uploads them under this ID (--basin ${f.basin_id}).` })
      setF(START); setPicked(null); onSaved()
    } catch (err) { setMessage({ ok: false, text: err instanceof ApiError ? err.message : 'Could not save.' }) }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0 0' }}>
      <CitySearch picked={picked} onPick={pick} />
      <div className="form-grid" style={{ alignItems: 'start' }}>
        {input('basin_id', 'Basin ID', 'The same name the bridge uploads with, e.g. S4-A', false)}
        {input('address', 'Address (optional)', '', false, false)}
        {input('latitude', 'Latitude', 'e.g. 45.4468')}
        {input('longitude', 'Longitude', 'e.g. -73.7513')}
        {input('sensor_depth_mm', 'Sensor depth from the grate (mm)', 'Tape it when you mount the sensor')}
        {input('invert_depth_mm', 'Outlet invert depth from the grate (mm, optional)', 'Profondeur du radier, if the plans have it. Leave empty: the sensor learns it from the resting water in about 2 dry days', true, false)}
        {select('diameter_mm', 'Basin internal diameter', [['405', '405 mm'], ['610', '610 mm (24" standard)'], ['915', '915 mm'], ['1220', '1220 mm']])}
        {select('outlet_mm', 'Outlet pipe diameter', ['150', '200', '250', '300', '375', '450'].map(v => [v, `${v} mm`] as [string, string]))}
        {select('sump_mm', 'Sump depth (réserve)', [['0', '0 mm'], ['300', '300 mm (default)'], ['500', '500 mm']])}
      </div>
      <label className="check"><input type="checkbox" checked={f.has_trap} onChange={e => setF({ ...f, has_trap: e.target.checked })} />Cast-iron trap (cloche) installed</label>
      {message && <div className={`notice ${message.ok ? 'ok' : 'error'}`} role={message.ok ? 'status' : 'alert'}>{message.text}</div>}
      <div><button type="submit" className="btn primary">Save basin</button></div>
    </form>
  )
}

export default function Basins() {
  const { data, error } = useData<OverviewData>('/overview')
  const { demo, refresh } = useView()
  const { user } = useAuth()
  const [params] = useSearchParams()
  const cityId = params.get('city')
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">Loading…</p>
  const mayAdd = !demo && (user?.role === 'admin' || user?.role === 'engineering')
  return (
    <>
      <div className="page-head"><div><h1>Basins</h1><p className="sub">{data.basins.length} monitored {data.basins.length === 1 ? 'basin' : 'basins'}, most urgent first. Click one for its detail.</p></div></div>
      {data.basins.length > 0 && <section className="card flush"><BasinTable rows={data.basins} /></section>}
      {mayAdd && <details className="card" open={data.basins.length === 0 || !!cityId}>
        <summary><b>Add a basin</b> <span className="muted">· from the city's list and its as-built plan; saving again with the same ID updates it</span></summary>
        <AddBasin onSaved={refresh} cityId={cityId} />
      </details>}
      {demo && <p className="sub">Basins are added in Live data. The pitch demo always shows the 12 scripted pilot basins.</p>}
    </>
  )
}
