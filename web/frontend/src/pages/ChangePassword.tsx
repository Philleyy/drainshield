import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { t } from '../i18n'

export default function ChangePassword() {
  const { user, refresh } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [done, setDone] = useState(false)
  const [busy, setBusy] = useState(false)
  const first = !!user?.must_change_password

  async function submit(e: FormEvent) {
    e.preventDefault()
    setError('')
    if (next !== confirm) { setError(t('The two new passwords are not the same.')); return }
    setBusy(true)
    try {
      await api('/auth/password', { body: { current, new: next } })
      await refresh()
      setDone(true)
      setCurrent(''); setNext(''); setConfirm('')
      if (first) navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Could not change the password.'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{first ? t('Choose your own password') : t('Change password')}</h1>
          <p className="sub">{first
            ? t('You signed in with a temporary password. Pick your own to continue.')
            : t('Signs you out on your other devices.')}</p>
        </div>
      </div>
      <form className="card" style={{ maxWidth: 480, display: 'flex', flexDirection: 'column', gap: 16 }} onSubmit={submit}>
        {error && <div className="notice error" role="alert">{error}</div>}
        {done && !first && <div className="notice ok" role="status">{t('Password changed.')}</div>}
        <div className="field">
          <label htmlFor="cur">{first ? t('Temporary password') : t('Current password')}</label>
          <input id="cur" type="password" autoComplete="current-password" value={current} onChange={e => setCurrent(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="new">{t('New password')}</label>
          <input id="new" type="password" autoComplete="new-password" value={next} onChange={e => setNext(e.target.value)} />
          <span className="hint">{t('At least 10 characters.')}</span>
        </div>
        <div className="field">
          <label htmlFor="new2">{t('New password again')}</label>
          <input id="new2" type="password" autoComplete="new-password" value={confirm} onChange={e => setConfirm(e.target.value)} />
        </div>
        <div className="row"><button className="btn primary" type="submit" disabled={busy || !current || !next}>{t('Save password')}</button></div>
      </form>
    </>
  )
}
