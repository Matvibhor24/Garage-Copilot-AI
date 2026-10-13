// Owner: sign in, then the live dashboard (Today) and stock (Stock).
import { useMemo, useState } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { api, requestId } from '../data/api.js'
import { confirmPhoneSignIn, MODE, session, signInDev, signOut, startPhoneSignIn } from '../data/auth.js'
import { useLiveView } from '../data/live.js'
import { actionDetail, actionLabel, clock, minutes, plate, rupees } from '../format.js'
import { Brand, CountUp, ErrorNote, LiveBadge, Skeleton, Spinner, useToast } from '../ui.jsx'
import JobViewer from '../vehicle3d/JobViewer.jsx'
import GarageFloor from '../garage3d/GarageFloor.jsx'
import OwnerVoice from './OwnerVoice.jsx'

export default function Owner() {
  const [me, setMe] = useState(() => (session()?.role === 'owner' ? session() : null))
  if (!me) return <OwnerSignIn onDone={setMe} />
  return <OwnerApp me={me} onSignOut={async () => { await signOut(); setMe(null) }} />
}

// ---------------------------------------------------------------- sign in

function OwnerSignIn({ onDone }) {
  const toast = useToast()
  const [phone, setPhone] = useState('+91 ')
  const [code, setCode] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [busy, setBusy] = useState(false)

  async function run(fn) {
    setBusy(true)
    try { await fn() } catch (e) { toast(e.message) } finally { setBusy(false) }
  }

  return (
    <main className="page page-narrow signin">
      <header className="topbar"><Brand /></header>
      <section className="stack enter" style={{ '--gap': '24px', paddingTop: 32 }}>
        <div className="stack" style={{ '--gap': '8px' }}>
          <span className="eyebrow">Owner</span>
          <h1>Your garage, live.</h1>
          <p className="muted">Jobs, approvals, stock and today's money. Nothing to type in.</p>
        </div>

        {MODE === 'firebase' && !confirmation && (
          <form className="stack" onSubmit={(e) => { e.preventDefault(); run(async () => setConfirmation(await startPhoneSignIn(phone.replace(/\s/g, ''), 'send-code'))) }}>
            <div className="field"><label htmlFor="phone">Phone number</label>
              <input id="phone" className="input" inputMode="tel" autoComplete="tel" value={phone} onChange={(e) => setPhone(e.target.value)} /></div>
            <button id="send-code" className="btn btn-primary btn-lg" disabled={busy || phone.replace(/\D/g, '').length < 12}>{busy ? <Spinner /> : 'Send code'}</button>
          </form>
        )}
        {MODE === 'firebase' && confirmation && (
          <form className="stack fade" onSubmit={(e) => { e.preventDefault(); run(async () => onDone(await confirmPhoneSignIn(api, confirmation, code))) }}>
            <div className="field"><label htmlFor="code">Code from SMS</label>
              <input id="code" className="input otp mono" inputMode="numeric" autoComplete="one-time-code" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))} autoFocus /></div>
            <button className="btn btn-primary btn-lg" disabled={busy || code.length !== 6}>{busy ? <Spinner /> : 'Sign in'}</button>
          </form>
        )}
        {MODE !== 'firebase' && (
          <div className="stack">
            <button className="btn btn-primary btn-lg" onClick={() => onDone(signInDev('shree-auto', 'o-asha', 'owner', 'Asha'))}>
              Continue as Asha · Shree Auto
            </button>
            {MODE === 'dev' && (
              <button className="btn btn-lg" onClick={() => onDone(signInDev('ganesh-motors', 'o-vikram', 'owner', 'Vikram'))}>
                Continue as Vikram · Ganesh Motors
              </button>
            )}
            <p className="muted small" style={{ textAlign: 'center' }}>
              {MODE === 'demo' ? 'Demo mode: sample data in this browser.' : 'Developer sign-in (backend running with AUTH_DISABLED=1).'}
            </p>
          </div>
        )}
      </section>
    </main>
  )
}

// ---------------------------------------------------------------- app

function OwnerApp({ me, onSignOut }) {
  const g = me.garage
  const dash = useLiveView(() => api('/api/owner/dashboard'), {
    animate: true,
    watch: [`garages/${g}/jobs`, `garages/${g}/quotes`, `garages/${g}/inventory`, `garages/${g}/reorder_asks`, `garages/${g}/messages`],
  })
  const d = dash.data
  return (
    <main className="page owner">
      <header className="topbar">
        <Brand to="/owner" />
        <div className="row" style={{ '--gap': '8px' }}>
          <LiveBadge />
          <button className="btn btn-ghost btn-sm" onClick={onSignOut}>Sign out</button>
        </div>
      </header>

      <div className="row between wrap owner-head enter">
        <div className="stack" style={{ '--gap': '2px' }}>
          <span className="eyebrow">{d ? `${d.garage.name} · ${d.garage.city}` : ' '}</span>
          <h1>{greeting()}, {me.name}</h1>
        </div>
        <nav className="tabs" aria-label="Owner sections">
          <NavLink end to="/owner" className="tab" viewTransition>Today</NavLink>
          <NavLink to="/owner/floor" className="tab" viewTransition>Floor</NavLink>
          <NavLink to="/owner/stock" className="tab" viewTransition>Stock</NavLink>
        </nav>
      </div>

      <ErrorNote error={dash.error} onRetry={dash.reload} />
      <Routes>
        <Route index element={<Today dash={dash} g={g} />} />
        <Route path="floor" element={dash.data ? <GarageFloor dash={dash.data} /> : <DashSkeleton />} />
        <Route path="stock" element={<Stock g={g} />} />
      </Routes>
      <OwnerVoice />
    </main>
  )
}

function greeting() {
  const h = Number(new Date().toLocaleString('en-IN', { hour: 'numeric', hour12: false, timeZone: 'Asia/Kolkata' }))
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening'
}

// ---------------------------------------------------------------- today

function Today({ dash, g }) {
  const d = dash.data
  if (!d) return <DashSkeleton />
  return (
    <div className="stack" style={{ '--gap': '20px' }}>
      {d.reorder_asks.map((a) => <AgentAsk key={a.part_id} ask={a} onDone={dash.reload} />)}

      <section className="tiles">
        <Tile i={0} label="Open jobs" value={d.open_jobs} />
        <Tile i={1} label="Pending approvals" value={d.pending_approvals.length} tone={d.pending_approvals.length ? 'warn' : ''}
          sub={d.pending_approvals[0] ? `${d.pending_approvals[0].id} · ${rupees(d.pending_approvals[0].total)}` : 'All clear'} />
        <Tile i={2} label="Low stock" value={d.low_stock.length} tone={d.low_stock.length ? 'bad' : ''}
          sub={d.low_stock[0] ? `${d.low_stock[0].name}: ${d.low_stock[0].qty} left` : 'Stock looks fine'} />
        <Tile i={3} label="Revenue today" value={d.revenue_today} format={rupees} tone="ok"
          sub={`${Object.keys(d.minutes_per_job).length} jobs closed`} />
      </section>

      <div className="owner-grid">
        <Board jobs={d.jobs} quotes={d.pending_approvals} />
        <Feed g={g} messages={d.messages} />
      </div>
    </div>
  )
}

function Tile({ label, value, sub, tone = '', format, i }) {
  return (
    <div className={`card tile tile-${tone} enter`} style={{ '--i': i }}>
      <span className="tile-label">{label}</span>
      <span className="tile-value"><CountUp value={value} format={format} /></span>
      {sub && <span className="tile-sub" key={sub}>{sub}</span>}
    </div>
  )
}

function AgentAsk({ ask, onDone }) {
  const toast = useToast()
  const [busy, setBusy] = useState('')
  async function answer(kind) {
    setBusy(kind)
    try {
      const out = await api(`/api/owner/inventory/${ask.part_id}/${kind}`, { method: 'POST', body: { request_id: requestId() } })
      toast(kind === 'reorder' ? `Ordered ${out.qty} from ${out.supplier}` : 'Okay, I will ask again tomorrow')
      onDone()
    } catch (e) {
      toast(e.message)
    } finally {
      setBusy('')
    }
  }
  return (
    <section className="card agent-ask pop" role="status">
      <span className="agent-spark" aria-hidden="true"><Spark /></span>
      <div className="grow stack" style={{ '--gap': '2px' }}>
        <span className="eyebrow" style={{ color: 'var(--accent)' }}>Agent</span>
        <p style={{ fontWeight: 550 }}>{ask.text}</p>
      </div>
      <div className="row" style={{ '--gap': '8px' }}>
        <button className="btn btn-accent btn-sm" onClick={() => answer('reorder')} disabled={!!busy}>{busy === 'reorder' ? <Spinner /> : 'Yes, reorder'}</button>
        <button className="btn btn-sm" onClick={() => answer('reorder-later')} disabled={!!busy}>Later</button>
      </div>
    </section>
  )
}

const COLUMNS = [
  { key: 'intake', label: 'Checked in' },
  { key: 'washing', label: 'Washing' },
  { key: 'service', label: 'In service' },
  { key: 'ready', label: 'Ready' },
]

function Board({ jobs, quotes }) {
  const [viewing, setViewing] = useState(null)
  const now = Date.now()
  const pendingFor = Object.fromEntries(quotes.map((q) => [q.job_id, q]))
  const column = (j) => (j.status === 'done' || j.stage === 'done' ? 'ready' : j.stage === 'waiting_approval' ? 'service' : j.stage)
  return (
    <section className="card board-card">
      <div className="row between" style={{ marginBottom: 14 }}>
        <h2>Jobs</h2>
        <span className="muted small">{jobs.filter((j) => j.status === 'open').length} on the floor</span>
      </div>
      <div className="board">
        {COLUMNS.map((c) => {
          const list = jobs.filter((j) => column(j) === c.key)
          return (
            <div key={c.key} className="board-col">
              <div className="board-col-head"><span>{c.label}</span><span className="count">{list.length}</span></div>
              {list.map((j) => (
                <article key={j.id} className={`job-card ${pendingFor[j.id] ? 'job-wait' : ''} ${j.status === 'done' ? 'job-done' : ''}`}
                  style={{ viewTransitionName: `job-${j.id}` }} role="button" tabIndex={0} aria-label={`Open ${j.id} in 3D`}
                  onClick={() => setViewing(j)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setViewing(j))}>
                  <div className="row between"><span className="mono small">{j.id}</span>
                    {j.status === 'done' ? <span className="chip chip-ok">{rupees(j.bill)}</span>
                      : <span className="muted small num">{minutes(Math.max(0, Math.round((now - new Date(j.stage_started_at)) / 60000)))}</span>}
                  </div>
                  <strong className="job-vehicle">{j.vehicle}</strong>
                  <span className="muted small">{plate(j.plate)} · {j.owner}</span>
                  {pendingFor[j.id] && <span className="chip chip-warn" style={{ marginTop: 6 }}>Waiting on {j.owner} · {rupees(pendingFor[j.id].total)}</span>}
                  <span className="job-mech small">{j.mechanic_name}</span>
                </article>
              ))}
              {!list.length && <div className="board-empty">—</div>}
            </div>
          )
        })}
      </div>
      {viewing && <JobViewer job={jobs.find((j) => j.id === viewing.id) || viewing} quote={pendingFor[viewing.id]} onClose={() => setViewing(null)} />}
    </section>
  )
}

function Feed({ g, messages }) {
  const [tab, setTab] = useState('activity')
  const audit = useLiveView(() => api('/api/owner/audit?limit=40'), { watch: [`garages/${g}/audit_log`] })
  return (
    <section className="card feed-card">
      <div className="row between" style={{ marginBottom: 10 }}>
        <h2>{tab === 'activity' ? 'Activity' : 'Messages'}</h2>
        <div className="seg">
          <button className={tab === 'activity' ? 'on' : ''} onClick={() => setTab('activity')}>Activity</button>
          <button className={tab === 'messages' ? 'on' : ''} onClick={() => setTab('messages')}>Messages</button>
        </div>
      </div>
      {tab === 'activity' ? (
        !audit.data ? <Skeleton h={200} /> : audit.data.length === 0 ? <div className="empty">Nothing yet today.</div> : (
          <ol className="feed">
            {audit.data.map((a) => (
              <li key={`${a.at}-${a.action}-${a.request_id || ''}`} className="feed-item fade">
                <span className={`who who-${a.by_role}`} aria-hidden="true">{a.by_name?.[0] || '?'}</span>
                <div className="grow">
                  <p><strong>{a.by_name}</strong> <span className="muted">{actionLabel(a.action)}</span></p>
                  <p className="small muted feed-detail">{actionDetail(a)}</p>
                </div>
                <span className="small muted num">{clock(a.at)}</span>
              </li>
            ))}
          </ol>
        )
      ) : messages.length === 0 ? <div className="empty">No messages sent yet.</div> : (
        <ol className="feed">
          {messages.map((m) => (
            <li key={m.id} className="feed-item fade">
              <span className={`who who-${m.channel}`} aria-hidden="true">{m.channel === 'whatsapp' ? <ChatIcon /> : m.channel === 'headset' ? <HeadsetIcon /> : <Spark />}</span>
              <div className="grow">
                <p className="small"><strong>{recipient(m)}</strong> <span className="muted">· {m.channel === 'whatsapp' ? 'WhatsApp (simulated)' : m.channel === 'headset' ? 'headset' : 'you'}</span></p>
                <p className="small msg-text">{m.text}</p>
              </div>
              <span className="small muted num">{clock(m.at)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  )
}

function recipient(m) {
  if (m.to === 'owner') return 'To you'
  if (m.to.startsWith('supplier:')) return m.to.slice(9)
  if (m.to.startsWith('c-')) return m.kind === 'quote' ? 'Customer · quote' : m.kind === 'final_bill' ? 'Customer · bill' : 'Customer'
  return 'Mechanic'
}

// ---------------------------------------------------------------- stock

function Stock({ g }) {
  const toast = useToast()
  const [q, setQ] = useState('')
  const [lowOnly, setLowOnly] = useState(false)
  const inv = useLiveView(() => api('/api/owner/inventory'), { watch: [`garages/${g}/inventory`] })
  const parts = useMemo(() => {
    const words = q.toLowerCase().split(/\s+/).filter(Boolean)
    return (inv.data || [])
      .filter((p) => !lowOnly || p.low_stock)
      .filter((p) => words.every((w) => `${p.name} ${p.fits.join(' ')}`.toLowerCase().includes(w)))
      .sort((a, b) => Number(b.low_stock) - Number(a.low_stock) || a.name.localeCompare(b.name))
  }, [inv.data, q, lowOnly])
  const max = Math.max(10, ...(inv.data || []).map((p) => p.qty))

  async function restock(p) {
    try {
      await api(`/api/owner/inventory/${p.id}/restock`, { method: 'POST', body: { qty: p.reorder_qty || 5, request_id: requestId() } })
      toast(`${p.name} +${p.reorder_qty || 5}`)
      inv.reload()
    } catch (e) {
      toast(e.message)
    }
  }

  return (
    <section className="card stock enter">
      <div className="row wrap" style={{ marginBottom: 14 }}>
        <input className="input grow" placeholder="Search parts or bikes…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search stock" />
        <button className={`btn ${lowOnly ? 'btn-primary' : ''}`} onClick={() => setLowOnly((v) => !v)} aria-pressed={lowOnly}>Low only</button>
      </div>
      {!inv.data ? <Skeleton h={320} /> : parts.length === 0 ? <div className="empty">No parts match.</div> : (
        <ul className="parts">
          {parts.map((p, i) => (
            <li key={p.id} className="part enter" style={{ '--i': Math.min(i, 12) }}>
              <div className="grow stack" style={{ '--gap': '2px' }}>
                <strong>{p.name}</strong>
                <span className="muted small">{p.fits.join(', ')}</span>
              </div>
              <div className="part-qty">
                <span className={`num ${p.low_stock ? 'qty-low' : ''}`}>{p.qty}</span>
                <span className="qty-bar"><span style={{ width: `${Math.min(100, (p.qty / max) * 100)}%` }} className={p.low_stock ? 'low' : ''} /></span>
              </div>
              <span className="num part-price">{rupees(p.price)}</span>
              {p.reorder_pending ? <span className="chip chip-ok">Ordered</span>
                : <button className="btn btn-sm" onClick={() => restock(p)}>+{p.reorder_qty || 5}</button>}
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function DashSkeleton() {
  return (
    <div className="stack">
      <div className="tiles">{[0, 1, 2, 3].map((i) => <Skeleton key={i} h={118} style={{ borderRadius: 24 }} />)}</div>
      <Skeleton h={360} style={{ borderRadius: 24 }} />
    </div>
  )
}

function Spark() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2l2.2 6.3L20 10.5l-5.8 2.2L12 19l-2.2-6.3L4 10.5l5.8-2.2z" /></svg>
}
function ChatIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z" /></svg>
}
function HeadsetIcon() {
  return <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M4 15v-3a8 8 0 0 1 16 0v3" /><rect x="3" y="14" width="4" height="6" rx="2" /><rect x="17" y="14" width="4" height="6" rx="2" /></svg>
}
