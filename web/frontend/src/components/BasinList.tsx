// The narrow list beside the map: one line per basin with the reason in words, tabs with counts.
// Picking a row lights up its pin; the card over the map opens the basin.
import { useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { num, plural, t } from '../i18n'
import { CATEGORY_COLOR } from './BasinMap'
import { CATEGORY_LABEL, chipClass, priorityText, type BasinRow } from './BasinTable'

type Tab = 'todo' | 'Offline' | 'Normal' | 'All'
const TABS: [Tab, string][] = [['todo', 'To handle'], ['Offline', 'Offline'], ['Normal', 'Normal'], ['All', 'All']]
const inTab = (tab: Tab, r: BasinRow) => tab === 'All' || (tab === 'todo' ? r.category === 'Urgent' || r.category === 'Inspect' : r.category === tab)

/** The reason in one line: what the sensor saw, else what to do. */
export function why(r: BasinRow) {
  if (r.why) return r.why
  if (r.live === 'backing_up' || r.live === 'high') return t('Water {water} below the street', { water: num(r.water) })
  return r.action
}

export default function BasinList({ rows, selected, onSelect, footer }: { rows: BasinRow[]; selected: string | null; onSelect: (id: string) => void; footer?: ReactNode }) {
  const [tab, setTab] = useState<Tab | null>(null)
  const shown: Tab = tab ?? (rows.some(r => inTab('todo', r)) ? 'todo' : 'All')
  const list = rows.filter(r => inTab(shown, r))
  return (
    <aside className="card flush side-list" aria-label={t('Basins')}>
      <div className="tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button key={k} type="button" role="tab" aria-selected={shown === k} onClick={() => setTab(k)}>
            {t(label)} <b>{rows.filter(r => inTab(k, r)).length}</b>
          </button>
        ))}
      </div>
      <div className="side-rows">
        {list.length === 0 && <p className="sub" style={{ padding: 16 }}>{t('Nothing here right now.')}</p>}
        {list.map(r => (
          <button key={r.id} type="button" className="side-row" aria-pressed={r.id === selected} onClick={() => onSelect(r.id)}>
            <i style={{ background: CATEGORY_COLOR[r.category] }} aria-hidden="true" />
            <span>
              <b>{r.id}</b> · {r.category === 'Normal' ? CATEGORY_LABEL.Normal : priorityText(r.priority)}
              <small>{r.category === 'Normal' ? r.address : why(r)}</small>
            </span>
            <time>{r.updated}</time>
          </button>
        ))}
      </div>
      {footer}
    </aside>
  )
}

/** The selected basin, over the map. */
export function MapCard({ row, onClose }: { row: BasinRow; onClose: () => void }) {
  return (
    <div className="map-card" role="status">
      <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <span className={`chip ${chipClass(row.category)}`}>{CATEGORY_LABEL[row.category] || row.category}</span>
          <h3 style={{ margin: '6px 0 2px' }}>{row.id} <span className="muted" style={{ fontWeight: 400 }}>· {row.address}</span></h3>
        </div>
        <button type="button" className="btn small" onClick={onClose} aria-label={t('Close')}>×</button>
      </div>
      {row.category !== 'Normal' && <p style={{ margin: '4px 0' }}>{why(row)}</p>}
      <p className="sub" style={{ margin: '4px 0 10px' }}>
        {row.category !== 'Normal' && <>{row.action} · </>}{row.water !== '—' && <>{t('Water {water} below the street', { water: num(row.water) })} · </>}{row.updated}
      </p>
      <Link className="btn small primary" to={`/basins/${row.id}`}>{t('Open the basin')} →</Link>
    </div>
  )
}

export const toHandle = (rows: BasinRow[]) => rows.filter(r => r.category === 'Urgent' || r.category === 'Inspect')
export const countLine = (n: number) => (n ? plural(n, '{n} basin to handle', '{n} basins to handle') : t('Nothing to handle'))
