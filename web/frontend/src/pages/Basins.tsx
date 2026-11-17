import { useState, type FormEvent } from 'react'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import BasinTable from '../components/BasinTable'
import { useData, useView } from '../view'
import type { OverviewData } from './Overview'

const START = { basin_id: '', address: '', latitude: '', longitude: '', diameter_mm: '610', invert_depth_mm: '1400', outlet_mm: '250', sump_mm: '300', sensor_depth_mm: '400', has_trap: true }
const NUMBERS = ['latitude', 'longitude', 'diameter_mm', 'invert_depth_mm', 'outlet_mm', 'sump_mm', 'sensor_depth_mm'] as const

/** The as-built form: what a city knows from its plans (pipe depth and diameters), not catalogue part names. */
function AddBasin({ onSaved }: { onSaved: () => void }) {
  const [f, setF] = useState(START)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const set = (k: keyof typeof START) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  const select = (k: keyof typeof START, label: string, options: [string, string][]) => (
    <div className="field"><label htmlFor={k}>{label}</label>
      <select id={k} value={String(f[k])} onChange={set(k)}>{options.map(([v, t]) => <option key={v} value={v}>{t}</option>)}</select></div>
  )
  const input = (k: keyof typeof START, label: string, hint = '', numeric = true) => (
    <div className="field"><label htmlFor={k}>{label}</label>
      <input id={k} value={String(f[k])} onChange={set(k)} inputMode={numeric ? 'decimal' : undefined} required={k !== 'address'} />
      {hint && <span className="hint">{hint}</span>}</div>
  )
  async function submit(e: FormEvent) {
    e.preventDefault()
    const body: Record<string, unknown> = { ...f }
    for (const k of NUMBERS) body[k] = Number(String(f[k]).replace(',', '.'))
    if (NUMBERS.some(k => !Number.isFinite(body[k] as number))) { setMessage({ ok: false, text: 'Latitude, longitude and depths must be numbers.' }); return }
    try {
      const r = await api<{ warnings: string[] }>('/basins', { body })
      setMessage({ ok: true, text: `Saved ${f.basin_id}. ${r.warnings.join(' ')} Its readings appear here once a bridge uploads them under this ID (--basin ${f.basin_id}).` })
      setF(START); onSaved()
    } catch (err) { setMessage({ ok: false, text: err instanceof ApiError ? err.message : 'Could not save.' }) }
  }
  return (
    <form onSubmit={submit} style={{ display: 'flex', flexDirection: 'column', gap: 14, padding: '4px 0 0' }}>
      <div className="form-grid" style={{ alignItems: 'start' }}>
        {input('basin_id', 'Basin ID', 'The same name the bridge uploads with, e.g. S4-A', false)}
        {input('address', 'Address (optional)', '', false)}
        {input('latitude', 'Latitude', 'e.g. 45.4468')}
        {input('longitude', 'Longitude', 'e.g. -73.7513')}
        {select('diameter_mm', 'Basin internal diameter', [['405', '405 mm'], ['610', '610 mm (24" standard)'], ['915', '915 mm'], ['1220', '1220 mm']])}
        {input('invert_depth_mm', 'Outlet invert depth from the grate (mm)', 'Profondeur du radier on the as-built plan')}
        {select('outlet_mm', 'Outlet pipe diameter', ['150', '200', '250', '300', '375', '450'].map(v => [v, `${v} mm`] as [string, string]))}
        {select('sump_mm', 'Sump depth (réserve)', [['0', '0 mm'], ['300', '300 mm (default)'], ['500', '500 mm']])}
        {input('sensor_depth_mm', 'Sensor depth from the grate (mm)')}
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
  if (error) return <div className="notice error" role="alert">{error}</div>
  if (!data) return <p className="muted">Loading…</p>
  const mayAdd = !demo && (user?.role === 'admin' || user?.role === 'engineering')
  return (
    <>
      <div className="page-head"><div><h1>Basins</h1><p className="sub">{data.basins.length} monitored {data.basins.length === 1 ? 'basin' : 'basins'}, most urgent first. Click one for its detail.</p></div></div>
      {data.basins.length > 0 && <section className="card flush"><BasinTable rows={data.basins} /></section>}
      {mayAdd && <details className="card" open={data.basins.length === 0}>
        <summary><b>Add a basin</b> <span className="muted">· from its as-built plan; saving again with the same ID updates it</span></summary>
        <AddBasin onSaved={refresh} />
      </details>}
      {demo && <p className="sub">Basins are added in Live data. The pitch demo always shows the 12 scripted pilot basins.</p>}
    </>
  )
}
