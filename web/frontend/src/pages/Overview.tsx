import { Link } from 'react-router-dom'
import { useAuth } from '../auth'
import { isOnline, useSensors } from './Sensors'

export default function Overview() {
  const { user } = useAuth()
  const { sensors } = useSensors(30_000)
  const now = Date.now()
  const online = (sensors || []).filter(s => isOnline(s, now)).length
  const total = sensors?.length ?? 0
  const firstName = (user?.name || '').split(' ')[0]

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{firstName ? `Hello, ${firstName}` : 'Overview'}</h1>
          <p className="sub">DrainShield web app, step 1: accounts, sign-in and live sensor uploads.</p>
        </div>
      </div>

      <div className="notice warn">
        The full overview (storm timeline, sector map, pre-storm runs) is being built now. Until then, the
        Streamlit dashboard stays the reference for the pitch demo.
      </div>

      <section className="grid-kpi" aria-label="Sensors">
        <div className="card">
          <div className="eyebrow">Sensors reporting</div>
          <div className="big">{sensors ? `${online} of ${total}` : '…'}</div>
          <p className="sub">{total ? 'Online = a reading in the last 70 min.' : 'No sensor has sent data yet.'}</p>
        </div>
        <div className="card">
          <div className="eyebrow">Readings stored</div>
          <div className="big">{sensors ? sensors.reduce((n, s) => n + s.readings_total, 0).toLocaleString('en-CA') : '…'}</div>
          <p className="sub">Each kept once, even if a bridge sends it twice.</p>
        </div>
      </section>

      <section className="card" aria-label="Next steps">
        <h2>What you can do now</h2>
        <ul style={{ margin: '10px 0 0', paddingLeft: 20, display: 'grid', gap: 6 }}>
          <li><Link to="/sensors">Sensors</Link>: the latest reading from each sensor, and its last 50 readings.</li>
          {user?.role === 'admin' && <>
            <li><Link to="/admin/accounts">Accounts</Link>: add your teammates and a demo account for the judges.</li>
            <li><Link to="/admin/keys">Sensor upload keys</Link>: make a key so the bench laptop can send readings here.</li>
          </>}
          <li><Link to="/account/password">Change password</Link></li>
        </ul>
      </section>
    </>
  )
}
