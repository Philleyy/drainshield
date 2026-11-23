// Which data every page shows: live, or the pitch demo at one minute of its scripted day (shared by all pages).
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, ApiError } from './api'
import { useAuth } from './auth'
import { lang, locale, t } from './i18n'

interface View {
  demo: boolean; locked: boolean; setDemo: (d: boolean) => void
  minute: number; setMinute: (m: number) => void; playing: boolean; setPlaying: (p: boolean) => void
  dark: boolean; setDark: (d: boolean) => void
  version: number; refresh: () => void
  url: (path: string, params?: Record<string, string>) => string
}
const ViewContext = createContext<View | null>(null)
const LAST = 24 * 60 - 15

function saved(store: Storage | undefined, key: string) {
  try { return store?.getItem(key) ?? null } catch { return null }        // private mode: nothing remembered
}
function save(store: Storage | undefined, key: string, value: string) {
  try { store?.setItem(key, value) } catch { /* not remembered */ }
}

export function ViewProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const locked = user?.role === 'demo'                                    // demo accounts only ever see the demo
  const [demoChoice, setDemoChoice] = useState(() => saved(window.sessionStorage, 'ds_demo') === '1')
  const [minute, setMinuteState] = useState(() => Number(saved(window.sessionStorage, 'ds_minute')) || 0)
  const [playing, setPlaying] = useState(false)
  const [dark, setDarkState] = useState(() => saved(window.localStorage, 'ds_dark') === '1')
  const [version, setVersion] = useState(0)
  const demo = locked || demoChoice

  const setMinute = useCallback((m: number) => {
    const v = Math.max(0, Math.min(LAST, m))
    setMinuteState(v)
    save(window.sessionStorage, 'ds_minute', String(v))
  }, [])
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light' }, [dark])
  useEffect(() => {                                                       // play: 15 demo minutes every 1.5 s
    if (!playing || !demo) return
    const id = window.setInterval(() => setMinuteState(m => { if (m >= LAST) { setPlaying(false); return m } return m + 15 }), 1500)
    return () => window.clearInterval(id)
  }, [playing, demo])
  useEffect(() => {                                                       // live data: look again every 5 s
    if (demo) return
    const id = window.setInterval(() => setVersion(v => v + 1), 5_000)
    return () => window.clearInterval(id)
  }, [demo])

  const value = useMemo<View>(() => ({
    demo, locked, minute, setMinute, playing, setPlaying, dark, version,
    setDemo: d => { setDemoChoice(d); setPlaying(false); save(window.sessionStorage, 'ds_demo', d ? '1' : '0') },
    setDark: d => { setDarkState(d); save(window.localStorage, 'ds_dark', d ? '1' : '0') },
    refresh: () => setVersion(v => v + 1),
    url: (path, params = {}) => {
      const q = new URLSearchParams(params)
      if (demo) { q.set('demo', '1'); q.set('t', String(minute)) }
      if (lang === 'en') q.set('lang', 'en')                                // the server answers in French by default
      return q.toString() ? `${path}?${q}` : path
    },
  }), [demo, locked, minute, setMinute, playing, dark, version])
  return <ViewContext.Provider value={value}>{children}</ViewContext.Provider>
}

export function useView() {
  const v = useContext(ViewContext)
  if (!v) throw new Error('useView outside ViewProvider')
  return v
}

/** Loads a page's data for the current view; keeps showing the last answer while the next one loads.
 * One request at a time, latest wins: dragging the demo slider or playing it used to queue a request per step,
 * each 1-2 s on the server, and the page fell further and further behind. */
export function useData<T>(path: string, params?: Record<string, string>) {
  const { url, version } = useView()
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState('')
  const target = url(path, params)
  const wanted = useRef({ target, version })
  const busy = useRef(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    wanted.current = { target, version }
    if (busy.current) return                                // the running loop picks up the newest wish
    busy.current = true
    void (async () => {
      let done: { target: string; version: number } | null = null
      while (alive.current && wanted.current !== done) {
        done = wanted.current
        try {
          const d = await api<T>(done.target)
          if (alive.current) { setData(d); setError('') }
        } catch (e) {
          if (alive.current && done === wanted.current) setError(e instanceof ApiError ? e.message : t('Could not load the data.'))
        }
      }
      busy.current = false
    })()
  }, [target, version])
  return { data, error }
}

export const hhmm = (minute: number) => `${String(Math.floor(minute / 60)).padStart(2, '0')}:${String(minute % 60).padStart(2, '0')}`
export const clock = (iso: string | null) => (iso ? iso.slice(11, 16) : '')
export const day = (iso: string) => new Date(iso).toLocaleDateString(locale, { month: 'short', day: 'numeric' })
export const minutesBetween = (fromIso: string, toIso: string) => Math.round((new Date(toIso).getTime() - new Date(fromIso).getTime()) / 60000)
export function duration(min: number) {
  const h = Math.floor(min / 60)
  return h ? `${h} h ${String(min % 60).padStart(2, '0')} min` : `${min} min`
}

interface Story { day: string; events: { minute: number; time: string; title: string; text: string }[] }

/** The demo clock: what is happening now in the story, a time slider, play, and jump to a moment. */
export function ClockBar() {
  const { minute, setMinute, playing, setPlaying, refresh } = useView()
  const [story, setStory] = useState<Story | null>(null)
  useEffect(() => { api<Story>(lang === 'en' ? '/demo?lang=en' : '/demo').then(setStory).catch(() => setStory(null)) }, [])
  const event = story?.events.filter(e => e.minute <= minute).pop()
  return (
    <section className="card clockbar no-print" aria-label={t('Pitch demo clock')}>
      <div style={{ flex: '1 1 320px' }}>
        <div className="eyebrow">{t('Pitch demo')} · {story?.day} · {hhmm(minute)}</div>
        {event && <><b>{event.time} · {event.title}</b><p className="sub">{event.text}</p></>}
      </div>
      <div className="clock-controls">
        <label htmlFor="demo-time" className="label">{t('Time of day')}</label>
        <input id="demo-time" type="range" min={0} max={LAST} step={5} value={minute}
          onChange={e => setMinute(Number(e.target.value))} />
        <div className="row">
          <button type="button" className="btn small primary" onClick={() => setPlaying(!playing)}>{playing ? t('Pause') : t('Play')}</button>
          <label htmlFor="demo-jump" className="sr-only">{t('Jump to a moment')}</label>
          <select id="demo-jump" className="btn small" value="" onChange={e => { if (e.target.value) setMinute(Number(e.target.value)) }}>
            <option value="">{t('Jump to a moment…')}</option>
            {story?.events.map(e => <option key={e.minute} value={e.minute}>{e.time} · {e.title}</option>)}
          </select>
          <button type="button" className="btn small" title={t('Remove what viewers clicked during the demo')}
            onClick={async () => { await api('/demo/reset', { body: {} }); refresh() }}>{t('Reset')}</button>
        </div>
      </div>
    </section>
  )
}
