import { useState, type FormEvent } from 'react'
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError, type User } from '../api'
import { useAuth } from '../auth'
import { Logo } from '../components/Shell'
import { t } from '../i18n'

export function WindowChart() {
  return (
    <div className="window-chart" aria-hidden="true">
      <svg viewBox="0 0 480 122" style={{ display: 'block', width: '100%', height: 'auto' }}>
        <rect x="20" y="10" width="200" height="88" fill="#fff4e3" />
        <text x="28" y="28" fontSize="12" fontWeight="600" fill="#8a4b00">{t('Safe cleaning window')}</text>
        <rect x="20" y="74" width="70" height="12" rx="4" fill="#1d5fd1" />
        <line x1="0" y1="98" x2="480" y2="98" stroke="#c9d2d9" />
        <g fill="#2f7fd6">
          <rect x="230" y="86" width="20" height="12" rx="3" /><rect x="256" y="64" width="20" height="34" rx="3" />
          <rect x="282" y="26" width="20" height="72" rx="3" /><rect x="308" y="64" width="20" height="34" rx="3" />
          <rect x="334" y="80" width="20" height="18" rx="3" />
        </g>
        <line x1="20" y1="4" x2="20" y2="104" stroke="#14202b" strokeWidth="2" />
        <text x="20" y="118" textAnchor="middle" fontSize="11" fontWeight="700" fill="#14202b">{t('Now')}</text>
        <text x="292" y="118" textAnchor="middle" fontSize="11" fill="#5f6b76">{t('Storm')}</text>
      </svg>
    </div>
  )
}

export function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="auth">
      <section className="auth-intro" aria-label={t('About DrainShield')}>
        <div className="row"><Logo /><b style={{ fontSize: 20 }}>DrainShield</b></div>
        <h1>{t('Clean the right catch basins before the rain.')}</h1>
        <p>{t('Environment Canada forecasts and live water levels from your basins, turned into one pre-storm run for your crews.')}</p>
        <WindowChart />
      </section>
      {children}
    </div>
  )
}

export default function SignIn() {
  const { user, refresh } = useAuth()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [remember, setRemember] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const next = params.get('next') || '/'
  const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/'
  if (user) return <Navigate to={user.must_change_password ? '/account/password' : safeNext} replace />

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const { user } = await api<{ user: User }>('/auth/login', { body: { email, password, remember } })
      await refresh()
      navigate(user.must_change_password ? '/account/password' : safeNext, { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Could not sign in.'))
      setBusy(false)
    }
  }

  return (
    <AuthLayout>
      <form className="auth-card" onSubmit={submit} noValidate>
        <div>
          <h2>{t('Sign in')}</h2>
          <p className="sub">{t('Dorval Public Works')}</p>
        </div>
        {error && <div className="notice error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="email">{t('Email')}</label>
          <input id="email" type="email" autoComplete="email" placeholder="name@dorval.ca" required
            value={email} onChange={e => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="password">{t('Password')}</label>
          <input id="password" type="password" autoComplete="current-password" required
            value={password} onChange={e => setPassword(e.target.value)} />
        </div>
        <label className="check">
          <input type="checkbox" checked={remember} onChange={e => setRemember(e.target.checked)} />
          {t('Keep me signed in for 30 days')}
        </label>
        <button className="btn primary" type="submit" disabled={busy || !email || !password}>
          {busy ? t('Signing in…') : t('Sign in')}
        </button>
        <p className="sub" style={{ margin: 0 }}>
          {t('Forgot your password or need an account? Ask your DrainShield administrator. Judges: use the demo login on your invitation.')}
        </p>
      </form>
    </AuthLayout>
  )
}
