import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { initials, ROLE_LABEL } from '../api'
import { useAuth } from '../auth'
import { lang, setLang, t } from '../i18n'
import { ClockBar, useView } from '../view'

const icon = {
  overview: <path d="M3 13h4l3-8 4 14 3-6h4" />,
  runs: <><path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
  crew: <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6M9 12h6M9 16h3" /></>,
  basins: <path d="M12 3c-3 4-6 7-6 11a6 6 0 0012 0c0-4-3-7-6-11z" />,
  sensors: <><path d="M5 12a7 7 0 0114 0M8 12a4 4 0 018 0" /><path d="M12 13v7" /></>,
  people: <><circle cx="9" cy="8" r="3.5" /><path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5M16 4.8a3.5 3.5 0 010 6.4M18.5 14.8c1.5.8 2.6 2.5 3 5.2" /></>,
  key: <><circle cx="8" cy="15" r="4" /><path d="M11 12l9-9M16 7l3 3M14 9l2 2" /></>,
  lock: <><rect x="5" y="11" width="14" height="9" rx="2" /><path d="M8 11V8a4 4 0 018 0v3" /></>,
  out: <path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10" />,
}

function Icon({ name }: { name: keyof typeof icon }) {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{icon[name]}</svg>
  )
}

export function Logo() {
  return (
    <span className="brand-mark">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2.2"
        strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 2l8 3v6c0 5-3.5 9-8 11-4.5-2-8-6-8-11V5l8-3z" /></svg>
    </span>
  )
}

function Segmented({ label, options, value, onChange }: { label: string; options: [string, string][]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" aria-pressed={v === value} onClick={() => onChange(v)}>{text}</button>
      ))}
    </div>
  )
}

export default function Shell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth()
  const { demo, locked, setDemo, dark, setDark } = useView()
  const navigate = useNavigate()
  if (!user) return null
  const link = ({ isActive }: { isActive: boolean }) => `nav-link${isActive ? ' active' : ''}`

  return (
    <div className="shell">
      <nav className="sidebar no-print" aria-label={t('Main')}>
        <NavLink to="/" className="brand" end>
          <Logo />
          <span><b>DrainShield</b><small>{t('Dorval · Public Works')}</small></span>
        </NavLink>
        <NavLink to="/" end className={link}><Icon name="overview" />{t('Overview')}</NavLink>
        <NavLink to="/run" className={link}><Icon name="runs" />{t('Pre-storm run')}</NavLink>
        <NavLink to="/crew" className={link}><Icon name="crew" />{t('Crew view')}</NavLink>
        <NavLink to="/basins" className={link}><Icon name="basins" />{t('Basins')}</NavLink>
        <NavLink to="/sensors" className={link}><Icon name="sensors" />{t('Sensors')}</NavLink>
        {user.role === 'admin' && <>
          <div className="nav-section">{t('Administration')}</div>
          <NavLink to="/admin/accounts" className={link}><Icon name="people" />{t('Accounts')}</NavLink>
          <NavLink to="/admin/keys" className={link}><Icon name="key" />{t('Sensor upload keys')}</NavLink>
        </>}
        <div className="grow" />
        {!locked && <Segmented label={t('Data')} value={demo ? 'demo' : 'live'} onChange={v => setDemo(v === 'demo')}
          options={[['live', t('Live')], ['demo', t('Pitch demo')]]} />}
        <Segmented label={t('Theme')} value={dark ? 'dark' : 'light'} onChange={v => setDark(v === 'dark')}
          options={[['light', t('Light')], ['dark', t('Dark')]]} />
        <Segmented label={t('Language')} value={lang} onChange={v => { if (v !== lang) setLang(v as 'fr' | 'en') }}
          options={[['fr', 'Français'], ['en', 'English']]} />
        <NavLink to="/account/password" className={link}><Icon name="lock" />{t('Change password')}</NavLink>
        <button type="button" className="nav-link" style={{ border: 0, background: 'transparent', cursor: 'pointer', textAlign: 'left' }}
          onClick={async () => { await signOut(); navigate('/signin') }}><Icon name="out" />{t('Sign out')}</button>
        <div className="me">
          <span className="avatar">{initials(user.name, user.email)}</span>
          <span><b>{user.name || user.email}</b><small>{ROLE_LABEL[user.role]}</small></span>
        </div>
      </nav>
      <main className="content">
        {demo && <ClockBar />}
        {children}
      </main>
    </div>
  )
}
