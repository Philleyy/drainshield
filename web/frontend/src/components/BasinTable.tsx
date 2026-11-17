import { Link } from 'react-router-dom'
import { clock, day } from '../view'

export interface Step { label: string; at: string | null; done: boolean }
export interface BasinRow {
  id: string; address: string; sector: string; lat: number; lon: number; category: string; priority: string
  action: string; updated: string; dispatched: boolean; steps: Step[] | null
}
export const chipClass = (category: string) => ({ Urgent: 'urgent', Inspect: 'inspect', Offline: 'offline' }[category] || 'normal')
export const priorityText = (p: string) => (p === 'Inspect before storm' ? 'Clean before storm' : p)

/** The 4 steps of an issue as dots, with the latest finished step in words. */
export function Progress({ steps, dispatched }: { steps: Step[] | null; dispatched?: boolean }) {
  if (!steps) return dispatched ? <span className="chip neutral">Crew dispatched</span> : <span className="muted">—</span>
  const last = [...steps].reverse().find(s => s.done)
  return (
    <span className="progress" title={steps.map(s => `${s.done ? '✓' : '○'} ${s.label}`).join('\n')}>
      {steps.map(s => <i key={s.label} className={s.done ? 'done' : ''} />)}
      <span>{last ? `${last.label}${last.at ? ` · ${day(last.at)}, ${clock(last.at)}` : ''}` : 'Not started'}</span>
    </span>
  )
}

export default function BasinTable({ rows }: { rows: BasinRow[] }) {
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 760 }}>
        <thead><tr><th>Basin</th><th>Sector</th><th>Priority</th><th>What to do</th><th>Progress</th><th>Updated</th></tr></thead>
        <tbody>
          {rows.map(r => (
            <tr key={r.id}>
              <td><Link to={`/basins/${r.id}`} style={{ fontWeight: 600 }}>{r.id}</Link><small>{r.address}</small></td>
              <td>{r.sector}</td>
              <td><span className={`chip ${chipClass(r.category)}`}>{priorityText(r.priority)}</span></td>
              <td>{r.action}</td>
              <td><Progress steps={r.steps} dispatched={r.dispatched} /></td>
              <td className="muted" style={{ whiteSpace: 'nowrap' }}>{r.updated}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
