import { useState } from 'react'
import { Link } from 'react-router-dom'
import BasinMap from '../components/BasinMap'
import { chipClass, priorityText } from '../components/BasinTable'
import { isEmergency, spareText, StopList, useSendRun, type RunState } from '../components/Run'
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
  if (!o || !run) return <p className="muted">Loading…</p>

  const candidates = o.basins.filter(b => b.category !== 'Normal' && !b.dispatched)
  const sectorNames = [...new Set(candidates.map(b => b.sector))]
  const p = run.suggested
  const late = p?.spare_min != null && p.spare_min < 0
  let fitText = 'No rain in the forecast.'
  if (p?.spare_min != null) fitText = late ? 'Does not fit before the rain.' : 'Fits before the rain.'
  const toggle = (id: string) => setExclude(x => (x.includes(id) ? x.filter(i => i !== id) : [...x, id]))

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{p && isEmergency(p) ? 'Emergency dispatch' : 'Pre-storm run'} {candidates.length > 0 && <span className="chip inspect" style={{ verticalAlign: 'middle' }}>Draft</span>}</h1>
          <p className="sub">Every flagged basin that no crew has been sent to yet, urgent ones first, in the order that takes the least driving.</p>
        </div>
        {p && <div className="row no-print">
          {p.google[0] && <a className="btn" href={p.google[0]} target="_blank" rel="noreferrer">Open in Google Maps</a>}
          <button type="button" className="btn" onClick={() => window.print()}>Print / save as PDF</button>
          <button type="button" className="btn primary" disabled={busy} onClick={async () => { if (await send(exclude, leave || null)) setExclude([]) }}>Send to crew</button>
        </div>}
      </div>
      {sendError && <div className="notice error" role="alert">{sendError}</div>}

      {candidates.length === 0 && (
        <section className="card">
          <h2>Nothing to send</h2>
          <p className="sub">{run.sent
            ? <>The run sent at {clock(run.sent.sent)} covers every flagged basin: {run.sent.done} of {run.sent.stops.length} stops done. <Link to="/crew">Open the crew view</Link></>
            : 'No basin is flagged and every sensor is reporting.'}</p>
        </section>
      )}

      {p && <div className={`notice ${late ? 'warn' : 'ok'}`}>
        <b>{fitText}</b>{' '}
        Leaves {p.leave}, back at the yard {p.back} ({spareText(p)}) · {p.stops.length} stops · {p.drive_min} min driving · {p.service_min} min on site · {p.km} km
        {p.note && <><br />{p.note}</>}
      </div>}

      {candidates.length > 0 && <div className="split">
        <div className="no-print" style={{ flex: '1 1 320px', maxWidth: 420, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <section className="card" aria-label="Settings">
            <div className="field">
              <label htmlFor="leave">Truck leaves the yard at</label>
              <input id="leave" type="time" value={leave || p?.leave || ''} onChange={e => setLeave(e.target.value)} />
              <span className="hint">Default: the next quarter hour.</span>
            </div>
          </section>
          <section className="card flush" aria-label="Basins in this run">
            <div className="card-head"><h2>Basins in this run</h2></div>
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
            <section className="card flush" aria-label="Route map"><BasinMap points={o.basins} line={p.line} stops={p.stops} depot={p.depot} /></section>
            <section className="card" aria-label="Crew sheet"><h2 style={{ marginBottom: 10 }}>Crew sheet</h2><StopList stops={p.stops} /></section>
          </> : <section className="card"><p className="sub">Tick at least one basin.</p></section>}
        </div>
      </div>}
    </>
  )
}
