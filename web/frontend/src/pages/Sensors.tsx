import { Fragment, useCallback, useEffect, useState } from 'react'
import { ago, api, ApiError, localTime } from '../api'

export interface SensorRow {
  basin_id: string
  last_reading_at: string | null
  last_received_at: string | null
  distance_cm: number | null
  battery_v: number | null
  temp_c: number | null
  mode: string | null
  rssi: number | null
  flags: number | null
  readings_total: number
}

interface ReadingRow {
  timestamp: string
  received_at: string
  distance_cm: number | null
  battery_v: number | null
  temp_c: number | null
  flags: number
  mode: string | null
}

const OFFLINE_AFTER_MIN = 70          // dry mode reads every 30 min: two missed readings + margin = offline

export function isOnline(s: SensorRow, now = Date.now()) {
  return !!s.last_reading_at && now - new Date(s.last_reading_at).getTime() < OFFLINE_AFTER_MIN * 60_000
}

const FLAG_TEXT: [number, string][] = [
  [0x01, 'no echo'], [0x02, 'at the sensor\'s minimum range'], [0x04, 'suspect reading'],
  [0x08, 'possibly iced'], [0x10, 'clock gap'], [0x20, 'on USB power'],
]
export function flagText(flags: number | null) {
  return FLAG_TEXT.filter(([bit]) => (flags || 0) & bit).map(([, t]) => t).join(', ')
}

export function useSensors(everyMs = 5_000) {
  const [sensors, setSensors] = useState<SensorRow[] | null>(null)
  const [error, setError] = useState('')
  const load = useCallback(async () => {
    try {
      const r = await api<{ sensors: SensorRow[] }>('/sensors')
      setSensors(r.sensors)
      setError('')
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load the sensors.')
    }
  }, [])
  useEffect(() => {
    void load()
    const t = window.setInterval(load, everyMs)
    return () => window.clearInterval(t)
  }, [load, everyMs])
  return { sensors, error, reload: load }
}

function Detail({ basin }: { basin: string }) {
  const [rows, setRows] = useState<ReadingRow[] | null>(null)
  useEffect(() => {
    api<{ readings: ReadingRow[] }>(`/sensors/${encodeURIComponent(basin)}/readings?limit=50`)
      .then(r => setRows(r.readings)).catch(() => setRows([]))
  }, [basin])
  if (!rows) return <p className="sub" style={{ padding: '0 16px 14px' }}>Loading readings…</p>
  return (
    <div className="table-wrap">
      <table>
        <thead><tr><th>Measured</th><th>Distance to water</th><th>Battery</th><th>Temp.</th><th>Mode</th><th>Notes</th><th>Received</th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.timestamp}>
              <td>{localTime(r.timestamp)}</td>
              <td>{r.distance_cm == null ? 'no echo' : `${r.distance_cm.toFixed(1)} cm`}</td>
              <td>{r.battery_v == null ? '—' : `${r.battery_v.toFixed(2)} V`}</td>
              <td>{r.temp_c == null ? '—' : `${r.temp_c.toFixed(0)} °C`}</td>
              <td>{r.mode || '—'}</td>
              <td>{flagText(r.flags) || '—'}</td>
              <td>{localTime(r.received_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Sensors() {
  const { sensors, error } = useSensors()
  const [open, setOpen] = useState<string | null>(null)
  const now = Date.now()

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Sensors</h1>
          <p className="sub">Latest reading from every sensor that has sent data. Refreshes every 15 s. Times are Montréal time.</p>
        </div>
      </div>
      {error && <div className="notice error" role="alert">{error}</div>}
      <section className="card flush" aria-label="Sensors">
        {sensors && sensors.length === 0 ? (
          <div style={{ padding: 20 }}>
            <h2>No readings yet</h2>
            <p className="sub">Start <code>lora_bridge.py</code> or <code>sensor_bridge.py</code> on the laptop with an upload key
              (an administrator makes one under <b>Sensor upload keys</b>). Readings appear here within seconds.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Sensor (basin)</th><th>Status</th><th>Last reading</th><th>Distance to water</th><th>Battery</th><th>Mode</th><th>Readings</th></tr></thead>
              <tbody>
                {(sensors || []).map(s => {
                  const online = isOnline(s, now)
                  const notes = flagText(s.flags)
                  return (
                    <Fragment key={s.basin_id}>
                      <tr className="clickable" onClick={() => setOpen(open === s.basin_id ? null : s.basin_id)}
                        aria-expanded={open === s.basin_id}>
                        <td><b>{s.basin_id}</b>{notes && <small>{notes}</small>}</td>
                        <td><span className={`chip ${online ? 'normal' : 'offline'}`}>{online ? 'Online' : 'Offline'}</span></td>
                        <td>{ago(s.last_reading_at, now)}<small>{localTime(s.last_reading_at)}</small></td>
                        <td>{s.distance_cm == null ? 'no echo' : `${s.distance_cm.toFixed(1)} cm`}</td>
                        <td>{s.battery_v == null ? '—' : `${s.battery_v.toFixed(2)} V`}</td>
                        <td>{s.mode || '—'}</td>
                        <td>{s.readings_total.toLocaleString('en-CA')}</td>
                      </tr>
                      {open === s.basin_id && (
                        <tr><td colSpan={7} style={{ padding: 0, background: '#fbfbfc' }}><Detail basin={s.basin_id} /></td></tr>
                      )}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
