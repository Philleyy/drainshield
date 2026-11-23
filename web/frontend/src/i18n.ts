// French first: every text on the site is written in English in the code and looked up in FR below.
// The language is remembered per browser (French unless someone picks English).
import { FR } from './fr'

export type Lang = 'fr' | 'en'

function stored(): Lang {
  try { return window.localStorage.getItem('ds_lang') === 'en' ? 'en' : 'fr' } catch { return 'fr' }
}

export const lang: Lang = stored()
export const locale = lang === 'fr' ? 'fr-CA' : 'en-CA'
document.documentElement.lang = lang

/** Switching language reloads the page: simpler than re-rendering every text, and it happens once. */
export function setLang(l: Lang) {
  try { window.localStorage.setItem('ds_lang', l) } catch { /* not remembered */ }
  window.location.reload()
}

/** t('{n} stops', { n: 3 }) -> '3 arrêts' in French. A missing translation shows the English. */
export function t(en: string, vars: Record<string, string | number> = {}) {
  const text = lang === 'fr' ? FR[en] ?? en : en
  return text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m))
}

/** 3.9 -> "3,9" in French; also inside text like "0.86 m". */
export const num = (x: number | string) => (lang === 'fr' ? String(x).replace(/(\d)\.(\d)/g, '$1,$2') : String(x))
/** French puts a space before a colon. */
export const colon = (label: string) => (lang === 'fr' ? `${label} :` : `${label}:`)

/** "1 basin" / "3 basins": the noun follows the number (French counts 0 and 1 as singular). */
export function plural(n: number, one: string, many: string) {
  return t(n === 1 || (lang === 'fr' && n === 0) ? one : many, { n })
}
