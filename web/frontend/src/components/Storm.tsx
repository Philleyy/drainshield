// Storm mode: while it rains, the overview opens on the basins backing up, with a text ready for the on-call foreman.
import { useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api'
import { useAuth } from '../auth'
import { num, plural, t } from '../i18n'

export interface Alert { id: string; address: string; kind: 'backing_up' | 'high' | 'grate_suspect'; water: string; neighbours?: string[] }
export interface Storm { raining: boolean; alerts: Alert[] }
interface OnCall { oncall_name: string; oncall_phone: string }

const KIND: Record<Alert['kind'], { chip: string; title: string; sms: string }> = {
  backing_up: { chip: 'urgent', title: 'Backing up', sms: 'DrainShield: basin {id} ({address}) is backing up, water {water} below the street. Send a crew and slow-down signs.' },
  high: { chip: 'inspect', title: 'Not draining', sms: 'DrainShield: basin {id} ({address}) is not draining. Check it when possible.' },
  grate_suspect: { chip: 'inspect', title: 'Not taking water while its neighbours fill', sms: 'DrainShield: basin {id} ({address}) is not taking water while its neighbours fill. Leaves on the grate? Check it.' },
}

export const smsText = (a: Alert) => t(KIND[a.kind].sms, { id: a.id, address: a.address || '—', water: num(a.water) })
const smsLink = (phone: string, body: string) => `sms:${phone.replace(/[^\d+]/g, '')}?&body=${encodeURIComponent(body)}`

function CopyText({ text }: { text: string }) {
  const [done, setDone] = useState(false)
  return <button type="button" className="btn small" onClick={async () => {
    try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 2000) } catch { /* not allowed */ }
  }}>{done ? t('Copied') : t('Copy the message')}</button>
}

/** The on-call contact: a name and a phone number, set by administrators and engineering. */
function OnCallForm({ value, onSaved }: { value: OnCall; onSaved: (v: OnCall) => void }) {
  const [f, setF] = useState(value)
  const [msg, setMsg] = useState('')
  async function save(e: FormEvent) {
    e.preventDefault()
    try { onSaved(await api<OnCall>('/settings', { method: 'PUT', body: f })); setMsg(t('Saved.')) } catch (err) {
      setMsg(err instanceof ApiError ? err.message : t('Could not save.'))
    }
  }
  return (
    <form onSubmit={save} className="form-grid">
      <div className="field"><label htmlFor="oc-name">{t('On-call foreman')}</label>
        <input id="oc-name" value={f.oncall_name} onChange={e => setF({ ...f, oncall_name: e.target.value })} placeholder={t('e.g. Marc, night foreman')} /></div>
      <div className="field"><label htmlFor="oc-phone">{t('Cell phone')}</label>
        <input id="oc-phone" type="tel" value={f.oncall_phone} onChange={e => setF({ ...f, oncall_phone: e.target.value })} placeholder="514 555-0199" /></div>
      <button type="submit" className="btn">{t('Save')}</button>
      {msg && <p className="sub" role="status">{msg}</p>}
    </form>
  )
}

export default function StormPanel({ storm }: { storm: Storm }) {
  const { user } = useAuth()
  const [onCall, setOnCall] = useState<OnCall | null>(null)
  useEffect(() => { api<OnCall>('/settings').then(setOnCall).catch(() => setOnCall(null)) }, [])
  const mayEdit = user?.role === 'admin' || user?.role === 'engineering'
  const phone = onCall?.oncall_phone || ''
  const all = storm.alerts.map(smsText).join('\n')

  return (
    <section className="card storm" aria-label={t('Storm mode')}>
      <div className="row" style={{ alignItems: 'flex-start' }}>
        <div style={{ flex: '1 1 320px' }}>
          <div className="eyebrow storm-eyebrow">{t('Storm mode · storm in progress')}</div>
          <h1 style={{ marginTop: 6 }}>{storm.alerts.length
            ? plural(storm.alerts.length, '{n} basin needs a crew now', '{n} basins need a crew now')
            : t('No basin is backing up')}</h1>
          <p className="sub">{storm.alerts.length ? t('Sent as soon as the sensors see it, before residents call.') : t('Every monitored basin is keeping up with the rain.')}</p>
        </div>
        {storm.alerts.length > 1 && <div className="row">
          {phone && <a className="btn primary" href={smsLink(phone, all)}>{t('Text all to {name}', { name: onCall?.oncall_name || phone })}</a>}
          <CopyText text={all} />
        </div>}
      </div>

      {storm.alerts.length > 0 && <ul className="alerts">
        {storm.alerts.map(a => (
          <li key={a.id + a.kind}>
            <span className={`chip ${KIND[a.kind].chip}`}>{t(KIND[a.kind].title)}</span>
            <div>
              <Link to={`/basins/${a.id}`}><b>{a.id}</b></Link> · {a.address}
              <small>{a.kind === 'grate_suspect'
                ? t('Signal to validate in the pilot: neighbours {list} are filling, this basin stays flat.', { list: (a.neighbours || []).join(', ') })
                : t('Water {water} below the street', { water: num(a.water) })}</small>
            </div>
            <div className="row">
              {phone && <a className="btn small primary" href={smsLink(phone, smsText(a))}>{t('Text the foreman')}</a>}
              <CopyText text={smsText(a)} />
            </div>
          </li>
        ))}
      </ul>}

      <details>
        <summary className="sub">{phone ? t('On call: {name} · {phone}', { name: onCall?.oncall_name || '—', phone }) : t('No on-call foreman set yet')}</summary>
        <p className="sub">{t('"Text" opens your phone\'s messaging app with the message ready to send. Sending texts automatically needs an SMS provider, which is not connected yet.')}</p>
        {mayEdit && onCall && <OnCallForm value={onCall} onSaved={setOnCall} />}
      </details>
    </section>
  )
}
