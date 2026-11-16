import type { ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import { initials, ROLE_LABEL } from '../api'
import { useAuth } from '../auth'

const icon = {
  overview: <path d="M3 13h4l3-8 4 14 3-6h4" />,
  runs: <><path d="M3 7h11v9H3zM14 10h4l3 3v3h-7z" /><circle cx="7" cy="18" r="2" /><circle cx="17" cy="18" r="2" /></>,
  basins: <path d="M12 3c-3 4-6 7-6 11a6 6 0 0012 0c0-4-3-7-6-11z" />,
  sensors: <><path d="M5 12a7 7 0 0114 0M8 12a4 4 0 018 0" /><path d="M12 13v7" /></>,
  log: <path d="M4 6h16M4 12h16M4 18h10" />,
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

export default function Shell({ children }: { children: ReactNode }) {
  const { user, signOut } = useAuth()
  const navigate = useNavigate()
  if (!user) return null
  const link = ({ isActive }: { isActive: boolean }) => `nav-link${isActive ? ' active' : ''}`

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <NavLink to="/" className="brand" end>
          <Logo />
          <span><b>DrainShield</b><small>Dorval · Public Works</small></span>
        </NavLink>
        <NavLink to="/" end className={link}><Icon name="overview" />Overview</NavLink>
        <span className="nav-link soon" aria-disabled="true"><Icon name="runs" />Pre-storm runs<span className="tag">soon</span></span>
        <span className="nav-link soon" aria-disabled="true"><Icon name="basins" />Basins<span className="tag">soon</span></span>
        <NavLink to="/sensors" className={link}><Icon name="sensors" />Sensors</NavLink>
        <span className="nav-link soon" aria-disabled="true"><Icon name="log" />Maintenance log<span className="tag">soon</span></span>
        {user.role === 'admin' && <>
          <div className="nav-section">Administration</div>
          <NavLink to="/admin/accounts" className={link}><Icon name="people" />Accounts</NavLink>
          <NavLink to="/admin/keys" className={link}><Icon name="key" />Sensor upload keys</NavLink>
        </>}
        <div className="grow" />
        <NavLink to="/account/password" className={link}><Icon name="lock" />Change password</NavLink>
        <button type="button" className="nav-link" style={{ border: 0, background: 'transparent', cursor: 'pointer', textAlign: 'left' }}
          onClick={async () => { await signOut(); navigate('/signin') }}><Icon name="out" />Sign out</button>
        <div className="me">
          <span className="avatar">{initials(user.name, user.email)}</span>
          <span><b>{user.name || user.email}</b><small>{ROLE_LABEL[user.role]}</small></span>
        </div>
      </nav>
      <main className="content">{children}</main>
    </div>
  )
}
