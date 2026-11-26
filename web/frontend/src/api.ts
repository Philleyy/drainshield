// Small helper for talking to the Python server. Cookies are sent automatically (same site).
import { locale, t } from './i18n'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function messageFrom(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown })?.detail
  if (typeof detail === 'string') return t(detail)                   // the server's messages are English
  if (Array.isArray(detail) && detail.length) {
    // FastAPI validation errors: [{loc, msg}]
    const first = detail[0] as { msg?: string }
    return t((first.msg || 'Please check the form.').replace(/^Value error, /, ''))
  }
  return t(status >= 500 ? 'The server had a problem. Try again in a moment.' : 'Something went wrong.')
}

export async function api<T = unknown>(path: string, options: { method?: string; body?: unknown } = {}): Promise<T> {
  let res: Response
  try {
    res = await fetch(`/api${path}`, {
      method: options.method || (options.body !== undefined ? 'POST' : 'GET'),
      headers: options.body !== undefined ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      credentials: 'same-origin',
    })
  } catch {
    throw new ApiError(0, t('No connection to the server. Check your internet and try again.'))
  }
  const text = await res.text()
  let body: unknown = null
  try { body = text ? JSON.parse(text) : null } catch { body = null }
  if (!res.ok) throw new ApiError(res.status, messageFrom(body, res.status))
  return body as T
}

export type Role = 'admin' | 'engineering' | 'crew'

export interface User {
  id: number
  email: string
  name: string
  role: Role
  active: boolean
  must_change_password: boolean
  last_login_at: string | null
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: t('Administrator'),
  engineering: t('Engineering'),
  crew: t('Crew'),
}

export function initials(name: string, email: string) {
  const parts = (name || email).split(/[\s.@]+/).filter(Boolean)
  return ((parts[0]?.[0] || '') + (parts[1]?.[0] || '')).toUpperCase() || '?'
}

const timeFmt = new Intl.DateTimeFormat(locale, { timeZone: 'America/Toronto', month: 'short', day: 'numeric',
  hour: '2-digit', minute: '2-digit', hour12: false })

export function localTime(iso: string | null) {
  return iso ? timeFmt.format(new Date(iso)) : '—'
}

export function ago(iso: string | null, now = Date.now()) {
  if (!iso) return t('never')
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 60) return t('just now')
  const m = Math.round(s / 60)
  if (m < 60) return t('{d} ago', { d: `${m} min` })
  const h = Math.floor(m / 60)
  if (h < 48) return t('{d} ago', { d: `${h} h${m % 60 ? ` ${m % 60} min` : ''}` })
  return t('{d} ago', { d: t('{n} days', { n: Math.round(h / 24) }) })
}
