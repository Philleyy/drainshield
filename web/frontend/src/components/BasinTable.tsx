import { Link } from 'react-router-dom'
import { t } from '../i18n'
import { clock, day } from '../view'

export interface Step { label: string; at: string | null; done: boolean }
export interface Check { state: 'confirmed' | 'still_slow' | 'waiting'; cleaned_at: string; rain_at: string | null }
export interface BasinRow {
  id: string; address: string; sector: string; lat: number; lon: number; category: string; priority: string
  action: string; why: string; updated: string; dispatched: boolean; steps: Step[] | null; check: Check | null; live: string; water: string
}
export const chipClass = (category: string) => ({ Urgent: 'urgent', Inspect: 'inspect', Offline: 'offline' }[category] || 'normal')
// the server sends priorities as codes (the site reads them); they are only words here
export const priorityText = (p: string) => t(p === 'Inspect before storm' ? 'Clean before storm' : p)
export const CATEGORY_LABEL: Record<string, string> = {
  Urgent: t('Urgent'), Inspect: t('Inspect soon'), Offline: t('Sensor offline'), Normal: t('Draining normally'),
}

/** The 4 steps of an issue as dots, with the latest finished step in words. */
export function Progress({ steps, dispatched }: { steps: Step[] | null; dispatched?: boolean }) {
  if (!steps) return dispatched ? <span className="chip neutral">{t('Crew dispatched')}</span> : <span className="muted">—</span>
  const last = [...steps].reverse().find(s => s.done)
  return (
    <span className="progress" title={steps.map(s => `${s.done ? '✓' : '○'} ${s.label}`).join('\n')}>
      {steps.map(s => <i key={s.label} className={s.done ? 'done' : ''} />)}
      <span>{last ? `${last.label}${last.at ? ` · ${day(last.at)}, ${clock(last.at)}` : ''}` : t('Not started')}</span>
    </span>
  )
}

export default function BasinTable({ rows }: { rows: BasinRow[] }) {
  return (
    <div className="table-wrap">
      <table style={{ minWidth: 760 }}>
        <thead><tr><th>{t('Basin')}</th><th>{t('Sector')}</th><th>{t('Priority')}</th><th>{t('What to do')}</th><th>{t('Progress')}</th><th>{t('Updated')}</th></tr></thead>
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
