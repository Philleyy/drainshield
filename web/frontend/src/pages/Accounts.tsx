import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ago, api, ApiError, ROLE_LABEL, type Role, type User } from '../api'
import { useAuth } from '../auth'

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button type="button" className="btn small" onClick={async () => {
      try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000) } catch { /* ignore */ }
    }}>{copied ? 'Copied' : 'Copy'}</button>
  )
}
export { CopyButton }

const ROLE_HELP: Record<Role, string> = {
  admin: 'everything, plus accounts and upload keys',
  engineering: 'all pages and engineering detail',
  crew: 'field view: runs and basins',
  demo: 'for judges: the pitch demo',
}

export default function Accounts() {
  const { user: me } = useAuth()
  const [list, setList] = useState<User[] | null>(null)
  const [error, setError] = useState('')
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState<Role>('crew')
  const [busy, setBusy] = useState(false)
  const [shown, setShown] = useState<{ email: string; password: string } | null>(null)

  const load = useCallback(async () => {
    try { setList((await api<{ users: User[] }>('/users')).users) } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not load accounts.')
    }
  }, [])
  useEffect(() => { void load() }, [load])

  async function add(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setError(''); setShown(null)
    try {
      const r = await api<{ user: User; temporary_password: string }>('/users', { body: { email, name, role } })
      setShown({ email: r.user.email, password: r.temporary_password })
      setEmail(''); setName(''); setRole('crew')
      await load()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not add the account.')
    } finally { setBusy(false) }
  }

  async function patch(u: User, body: Partial<Pick<User, 'role' | 'active'>>) {
    setError('')
    try { await api(`/users/${u.id}`, { method: 'PATCH', body }); await load() } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not update the account.')
    }
  }

  async function reset(u: User) {
    if (!window.confirm(`Give ${u.email} a new temporary password? Their current password stops working.`)) return
    setError(''); setShown(null)
    try {
      const r = await api<{ temporary_password: string }>(`/users/${u.id}/reset-password`, { body: {} })
      setShown({ email: u.email, password: r.temporary_password })
      await load()
    } catch (err) { setError(err instanceof ApiError ? err.message : 'Could not reset the password.') }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Accounts</h1>
          <p className="sub">Only people with an account can sign in. New accounts get a temporary password and choose their own at first sign-in.</p>
        </div>
      </div>

      {error && <div className="notice error" role="alert">{error}</div>}
      {shown && (
        <div className="notice ok" role="status" style={{ display: 'grid', gap: 10 }}>
          <div>Temporary password for <b>{shown.email}</b>. Give it to them in person or by text. It is shown only once.</div>
          <div className="row"><span className="secret" style={{ flex: 1 }}>{shown.password}</span><CopyButton text={shown.password} /></div>
        </div>
      )}

      <form className="card" onSubmit={add} aria-label="Add an account">
        <h2 style={{ marginBottom: 12 }}>Add an account</h2>
        <div className="form-grid">
          <div className="field"><label htmlFor="n-name">Name</label>
            <input id="n-name" value={name} onChange={e => setName(e.target.value)} placeholder="Alex Tremblay" /></div>
          <div className="field"><label htmlFor="n-email">Email</label>
            <input id="n-email" type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="alex@dorval.ca" /></div>
          <div className="field"><label htmlFor="n-role">Role</label>
            <select id="n-role" value={role} onChange={e => setRole(e.target.value as Role)}>
              {(Object.keys(ROLE_LABEL) as Role[]).map(r => <option key={r} value={r}>{ROLE_LABEL[r]}: {ROLE_HELP[r]}</option>)}
            </select></div>
          <button className="btn primary" type="submit" disabled={busy || !email || !name}>Add account</button>
        </div>
      </form>

      <section className="card flush" aria-label="All accounts">
        <div className="table-wrap">
          <table>
            <thead><tr><th>Person</th><th>Role</th><th>Status</th><th>Last sign-in</th><th></th></tr></thead>
            <tbody>
              {(list || []).map(u => (
                <tr key={u.id}>
                  <td><b>{u.name}</b><small>{u.email}</small></td>
                  <td>
                    <label style={{ position: 'absolute', left: -9999 }} htmlFor={`role-${u.id}`}>Role of {u.email}</label>
                    <select id={`role-${u.id}`} value={u.role} onChange={e => patch(u, { role: e.target.value as Role })}
                      style={{ minHeight: 36, borderRadius: 7, border: '1px solid var(--border-strong)', padding: '0 8px', background: '#fff' }}>
                      {(Object.keys(ROLE_LABEL) as Role[]).map(r => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}
                    </select>
                  </td>
                  <td>
                    {!u.active ? <span className="chip offline">Disabled</span>
                      : u.must_change_password ? <span className="chip inspect">Temporary password</span>
                      : <span className="chip normal">Active</span>}
                  </td>
                  <td>{u.last_login_at ? ago(u.last_login_at) : 'never'}</td>
                  <td>
                    <div className="row" style={{ justifyContent: 'flex-end' }}>
                      <button type="button" className="btn small" onClick={() => reset(u)}>New temporary password</button>
                      {u.id !== me?.id && (u.active
                        ? <button type="button" className="btn small danger" onClick={() => patch(u, { active: false })}>Disable</button>
                        : <button type="button" className="btn small" onClick={() => patch(u, { active: true })}>Enable</button>)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
