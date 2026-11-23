// The municipality's catch basins (Ville de Montréal open data): loaded once, shared by the map and the add-basin form.
import { api } from './api'
import { t } from './i18n'

export interface CityBasin { id: string; address: string; lat: number; lon: number; type: string; provenance: string; tier: string }
let loading: Promise<CityBasin[]> | null = null

export function cityBasins() {
  loading ??= api<{ columns: string[]; rows: (string | number | null)[][] }>('/city-basins').then(d => {
    const at = (name: string) => d.columns.indexOf(name)
    const get = (r: (string | number | null)[], name: string) => (at(name) < 0 ? '' : String(r[at(name)] ?? ''))
    return d.rows.map(r => ({ id: get(r, 'municipal_id'), address: get(r, 'address'), lat: Number(get(r, 'latitude')), lon: Number(get(r, 'longitude')),
      type: get(r, 'basin_type'), provenance: get(r, 'provenance'), tier: get(r, 'tier_label') }))
  }).catch(e => { loading = null; throw e })
  return loading
}

/** How far off the city's position may be, from how it was surveyed. */
export function accuracy(provenance: string) {
  const p = provenance.toUpperCase()
  if (p.includes('TERRAIN')) return t('surveyed on site (±10 cm)')
  if (p.includes('PHOTO')) return t('from aerial photos (±30–40 cm)')
  if (p.includes('PLANS')) return t('from plans')
  if (p.includes('MAIN')) return t('hand-drawn (approximate)')
  return ''
}

/** Whether the sensor bracket fits, from the city's basin type. */
export function fit(type: string) {
  const u = type.toUpperCase()
  if (u.startsWith('CIRC')) return { ok: true, text: t('Round: fits the DrainShield bracket') }
  if (u.startsWith('INCON')) return { ok: false, text: t('Type unknown in the city records: check on site') }
  return { ok: false, text: t('{type}: bracket not designed for it yet', { type: type || t('Unknown type') }) }
}
