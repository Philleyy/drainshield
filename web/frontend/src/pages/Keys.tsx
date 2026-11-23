import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { ago, api, ApiError, localTime } from '../api'
import { CopyButton } from './Accounts'
import { t } from '../i18n'

interface Key { id: string; name: string; revoked: boolean; created_at: string; last_used_at: string | null }

export default function Keys() {
  const [keys, setKeys] = useState<Key[] | null>(null)
  const [name, setName] = useState('')
  const [fresh, setFresh] = useState('')
  const [error, setError] = useState('')
  const site = window.location.origin

  const load = useCallback(async () => {
    try { setKeys((await api<{ keys: Key[] }>('/keys')).keys) } catch (e) {
      setError(e instanceof ApiError ? e.message : t('Could not load keys.'))
    }
  }, [])
  useEffect(() => { void load() }, [load])

  async function create(e: FormEvent) {
    e.preventDefault()
    setError('')
    try {
      setFresh((await api<{ key: string }>('/keys', { body: { name } })).key)
      setName('')
      await load()
    } catch (err) { setError(err instanceof ApiError ? err.message : t('Could not make a key.')) }
  }

  async function revoke(k: Key) {
    if (!window.confirm(t('Stop key "{name}"? A bridge using it can no longer upload.', { name: k.name }))) return
    try { await api(`/keys/${k.id}`, { method: 'DELETE' }); await load() } catch (err) {
      setError(err instanceof ApiError ? err.message : t('Could not stop the key.'))
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('Sensor upload keys')}</h1>
          <p className="sub">{t('The laptop next to the LoRa receiver (or the USB sensor) uses a key to send readings here. One key per laptop.')}</p>
        </div>
      </div>
      {error && <div className="notice error" role="alert">{error}</div>}

      <form className="card" onSubmit={create} aria-label={t('Make a key')}>
        <div className="form-grid">
          <div className="field"><label htmlFor="k-name">{t('Where it will be used')}</label>
            <input id="k-name" value={name} onChange={e => setName(e.target.value)} placeholder={t('Bench laptop (LoRa receiver)')} /></div>
          <button className="btn primary" type="submit" disabled={!name}>{t('Make a key')}</button>
        </div>
      </form>

      {fresh && (
        <section className="card" aria-label={t('New key')} style={{ display: 'grid', gap: 12 }}>
          <div className="notice ok">{t('Your new key is below. Copy it now: it is shown only once.')}</div>
          <div className="row"><span className="secret" style={{ flex: 1 }}>{fresh}</span><CopyButton text={fresh} /></div>
          <div>
            <div className="label">{t('On the laptop, in the drainshield folder (PowerShell):')}</div>
            <pre>{`python lora_bridge.py COM5 --upload ${site} --key ${fresh}`}</pre>
            <div className="label">{t('or, for the USB sensor:')}</div>
            <pre>{`python sensor_bridge.py COM3 --basin TEST-01 --upload ${site} --key ${fresh}`}</pre>
            <p className="sub">{t("Replace COM5 / COM3 with your port (run the command without it to list ports). Readings keep being saved on the laptop too, and any that can't be sent wait in a queue until the internet is back.")}</p>
          </div>
        </section>
      )}

      <section className="card flush" aria-label={t('Keys')}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t('Key')}</th><th>{t('Made')}</th><th>{t('Last used')}</th><th>{t('Status')}</th><th></th></tr></thead>
            <tbody>
              {(keys || []).length === 0 && <tr><td colSpan={5} className="muted">{t('No keys yet.')}</td></tr>}
              {(keys || []).map(k => (
                <tr key={k.id}>
                  <td><b>{k.name}</b><small>dsk_{k.id}_…</small></td>
                  <td>{localTime(k.created_at)}</td>
                  <td>{k.last_used_at ? ago(k.last_used_at) : t('never')}</td>
                  <td>{k.revoked ? <span className="chip offline">{t('Stopped')}</span> : <span className="chip normal">{t('Active')}</span>}</td>
                  <td style={{ textAlign: 'right' }}>{!k.revoked &&
                    <button type="button" className="btn small danger" onClick={() => revoke(k)}>{t('Stop key')}</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  )
}
