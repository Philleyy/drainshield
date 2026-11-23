import { useEffect, useState, type FormEvent } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { AuthLayout } from './SignIn'
import { t } from '../i18n'

/** First run only: the administrator account is created with the one-time link from the setup token. */
export default function Setup() {
  const [params] = useSearchParams()
  const token = params.get('token') || ''
  const { refresh } = useAuth()
  const navigate = useNavigate()
  const [needed, setNeeded] = useState<boolean | null>(null)
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api<{ needed: boolean }>('/setup').then(r => setNeeded(r.needed)).catch(() => setNeeded(false))
  }, [])

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (password !== confirm) { setError(t('The two passwords are not the same.')); return }
    setBusy(true)
    try {
      await api('/setup', { body: { token, name, email, password } })
      await refresh()
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Setup failed.'))
      setBusy(false)
    }
  }

  if (needed === null) return <div className="center-screen">{t('Loading…')}</div>
  if (!needed || !token) {
    return (
      <AuthLayout>
        <div className="auth-card">
          <h2>{t('Setup is done')}</h2>
          <p className="sub" style={{ margin: 0 }}>{t('The administrator account already exists.')} <Link to="/signin">{t('Sign in')}</Link> {t('instead.')}</p>
        </div>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout>
      <form className="auth-card" onSubmit={submit} noValidate>
        <div>
          <h2>{t('Create the administrator')}</h2>
          <p className="sub">{t('First time only. This account can add the rest of your team.')}</p>
        </div>
        {error && <div className="notice error" role="alert">{error}</div>}
        <div className="field">
          <label htmlFor="name">{t('Your name')}</label>
          <input id="name" autoComplete="name" value={name} onChange={e => setName(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="email">{t('Email')}</label>
          <input id="email" type="email" autoComplete="email" value={email} onChange={e => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="pw">{t('Password')}</label>
          <input id="pw" type="password" autoComplete="new-password" value={password} onChange={e => setPassword(e.target.value)} />
          <span className="hint">{t('At least 10 characters. A short sentence is easy to remember.')}</span>
        </div>
        <div className="field">
          <label htmlFor="pw2">{t('Password again')}</label>
          <input id="pw2" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} />
        </div>
        <button className="btn primary" type="submit" disabled={busy || !name || !email || !password}>
          {busy ? t('Creating…') : t('Create account and sign in')}
        </button>
      </form>
    </AuthLayout>
  )
}
