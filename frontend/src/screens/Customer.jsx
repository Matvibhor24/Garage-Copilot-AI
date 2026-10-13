// The customer's page: /j/:token. No login. Live status, the quote with its photo, one-tap approval.
import { useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../data/api.js'
import { customerFirestore } from '../data/auth.js'
import { useLiveView } from '../data/live.js'
import { clock, minutes, plate, rupees } from '../format.js'
import { Check, CountUp, ErrorNote, LiveBadge, Skeleton, Spinner, useToast } from '../ui.jsx'
import Vehicle3D from '../vehicle3d/Vehicle3D.jsx'

const STEPS = [
  { key: 'intake', label: 'Checked in' },
  { key: 'washing', label: 'Washing' },
  { key: 'service', label: 'In service' },
  { key: 'ready', label: 'Ready for pickup' },
]

// The link token carries {g, j} in its signed payload; only used to know which docs to watch.
function linkPayload(token) {
  try {
    const b64 = token.split('.')[0].replace(/-/g, '+').replace(/_/g, '/')
    return JSON.parse(atob(b64))
  } catch {
    return {}
  }
}

export default function Customer() {
  const { token } = useParams()
  const { g, j } = linkPayload(token)
  const firestore = useMemo(() => (g ? customerFirestore(api, token).catch(() => null) : null), [token, g])
  const { data, error, loading, reload } = useLiveView(() => api(`/api/j/${token}`, { anonymous: true }), {
    deps: [token],
    firestore,
    watch: g ? [`garages/${g}/jobs/${j}`, `garages/${g}/jobs/${j}/stages`, [`garages/${g}/quotes`, 'job_id', '==', j]] : [],
  })

  if (loading) return <CustomerSkeleton />
  if (!data) {
    return (
      <main className="page page-narrow stack" style={{ paddingTop: 64 }}>
        <h1>Link not working</h1>
        <p className="muted">{error?.status === 403 ? 'This link has expired or is not valid. Ask the garage to send it again.' : error?.message}</p>
      </main>
    )
  }

  const done = data.status === 'done'
  const pending = data.quotes.filter((q) => q.status === 'pending')
  const decided = data.quotes.filter((q) => q.status !== 'pending' && q.status !== 'draft')

  return (
    <main className="page customer stack" style={{ '--gap': '16px' }}>
      <header className="topbar">
        <div className="stack" style={{ '--gap': '0px' }}>
          <span className="garage-name">{data.garage}</span>
          <span className="muted small">Job {data.job_id}</span>
        </div>
        <LiveBadge label="Live" />
      </header>

      <ErrorNote error={error} onRetry={reload} />

      {/* Phones: one column. Wide screens: the vehicle and status stay on the left, the rest on the right. */}
      <div className="customer-grid">
        <div className="customer-main">
          <section className={`card hero enter ${done ? 'hero-done' : ''}`}>
            <div className="row between wrap">
              <div className="stack" style={{ '--gap': '6px' }}>
                <span className="eyebrow">Your vehicle</span>
                <h2 style={{ fontSize: 24 }}>{data.vehicle}</h2>
              </div>
              <span className="plate mono">{plate(data.plate)}</span>
            </div>
            <Vehicle3D job={data} caption={false} />
            <div className="hero-status">
              {done ? <Check size={44} /> : <span className="status-pulse" aria-hidden="true" />}
              <div className="stack" style={{ '--gap': '2px' }}>
                <h1 className="status-title" key={data.stage_label}>{done ? 'Ready for pickup' : data.stage_label}</h1>
                <span className="muted small">{done ? `Final bill ${rupees(data.bill)}` : statusHint(data)}</span>
              </div>
            </div>
          </section>
        </div>

        <div className="customer-side stack" style={{ '--gap': '16px' }}>
          {pending.map((q) => <QuoteCard key={q.id} q={q} token={token} owner={data.owner} onDone={reload} />)}

          <section className="card enter" style={{ '--i': 1 }}>
            <h3 style={{ marginBottom: 12 }}>Progress</h3>
            <Timeline data={data} />
          </section>

          {decided.map((q, i) => (
            <section key={q.id} className="card card-flat row between enter" style={{ '--i': 2 + i }}>
              <div className="stack" style={{ '--gap': '2px' }}>
                <h3>Quote {q.id}</h3>
                <span className="muted small">{q.lines.map((l) => l.name).join(', ')} + labour</span>
              </div>
              <div className="stack" style={{ '--gap': '4px', alignItems: 'flex-end' }}>
                <span className="num" style={{ fontWeight: 650 }}>{rupees(q.total)}</span>
                <span className={`chip ${q.status === 'approved' ? 'chip-ok' : 'chip-bad'}`}>{q.status === 'approved' ? 'Approved' : 'Declined'}</span>
              </div>
            </section>
          ))}

          {(done || data.parts.length > 0) && <Bill data={data} done={done} />}
        </div>
      </div>

      <p className="muted small" style={{ textAlign: 'center', paddingTop: 8 }}>This page updates by itself. No app needed.</p>
    </main>
  )
}

function statusHint(data) {
  const last = data.timeline[data.timeline.length - 1]
  if (data.quotes.some((q) => q.status === 'pending')) return 'Waiting for your OK on extra work'
  return last ? `Since ${clock(last.started_at)}` : ''
}

function Timeline({ data }) {
  const at = {}
  for (const t of data.timeline) if (!at[t.name]) at[t.name] = t
  if (at.done && !at.ready) at.ready = at.done
  const stageKey = data.stage === 'done' ? 'ready' : data.stage === 'waiting_approval' ? 'service' : data.stage
  const current = Math.max(0, STEPS.findIndex((s) => s.key === stageKey))
  const doneAll = data.status === 'done'
  return (
    <ol className="timeline" style={{ '--progress': doneAll ? 1 : current / (STEPS.length - 1) }}>
      {STEPS.map((s, i) => {
        const state = doneAll || i < current ? 'done' : i === current ? 'now' : 'todo'
        const t = at[s.key]
        return (
          <li key={s.key} className={`tl-step tl-${state}`}>
            <span className="tl-dot" aria-hidden="true">{state === 'done' && <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 6.2 5 8.5l4.5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}</span>
            <span className="grow">{s.label}</span>
            <span className="muted small num">
              {state === 'now' && !doneAll ? <span className="chip chip-accent">now</span> : t ? (t.minutes != null && s.key !== 'ready' ? minutes(t.minutes) : clock(t.started_at)) : ''}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function QuoteCard({ q, token, owner, onDone }) {
  const toast = useToast()
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState(null)
  const [confirmReject, setConfirmReject] = useState(false)
  const [showOriginal, setShowOriginal] = useState(false)
  const sending = useRef(false)

  // One request per decision, even on a double tap (two taps can land before React re-renders).
  // The confirmation shows briefly, then the page reloads and the server decides what is shown: the quote moves
  // to the decided list, or, if it is somehow still pending, the buttons come back instead of a stale "Approved".
  async function decide(kind) {
    if (sending.current) return
    sending.current = true
    setBusy(kind)
    try {
      const out = await api(`/api/j/${token}/quotes/${q.id}/${kind}`, { method: 'POST', anonymous: true })
      // in_progress: the same decision is already being saved (e.g. from a second tab)
      setResult(out.status === 'in_progress' ? (kind === 'approve' ? 'approved' : 'rejected') : out.status)
      setTimeout(async () => { await onDone(); setResult(null); sending.current = false }, 1600)
    } catch (e) {
      sending.current = false
      if (e.status === 409) onDone() // already decided elsewhere: just show the current state, no error
      else toast(e.message)
    } finally {
      setBusy('')
    }
  }

  if (result) {
    return (
      <section className="card quote-done pop center stack" style={{ '--gap': '10px', textAlign: 'center' }}>
        {result === 'approved' ? <Check size={64} /> : <span className="decline-mark">✕</span>}
        <h2>{result === 'approved' ? 'Approved' : 'Declined'}</h2>
        <p className="muted">{result === 'approved' ? 'Thanks! The mechanic has been told to go ahead.' : 'No problem. Nothing extra will be done.'}</p>
      </section>
    )
  }

  return (
    <section className="card quote enter" aria-labelledby={`q-${q.id}`}>
      <div className="row between">
        <span className="chip chip-accent"><span className="dot live-dot" />Your approval needed</span>
        <span className="muted small">Quote {q.id}</span>
      </div>

      <h2 id={`q-${q.id}`} style={{ margin: '14px 0 4px' }}>Extra work found</h2>
      {q.note && <p className="muted">{capitalise(q.note)}.</p>}

      {q.photo_url && (
        <figure className="quote-photo">
          <img src={q.photo_url} alt={q.photo_caption || 'Photo from the mechanic'} />
          {q.photo_caption && <figcaption>“{q.photo_caption}”</figcaption>}
        </figure>
      )}

      <dl className="lines">
        {q.lines.map((l) => (
          <div key={l.part_id} className="line"><dt>{l.name}{l.qty > 1 ? ` × ${l.qty}` : ''}</dt><dd className="num">{rupees(l.total)}</dd></div>
        ))}
        <div className="line"><dt>Labour</dt><dd className="num">{rupees(q.labour)}</dd></div>
        <div className="line line-total"><dt>Total</dt><dd className="num"><CountUp value={q.total} format={rupees} /></dd></div>
      </dl>

      {q.text && q.lang && q.lang !== 'en' && (
        <div className="translated">
          <button className="link-btn" onClick={() => setShowOriginal((v) => !v)} aria-expanded={showOriginal}>
            {showOriginal ? 'Hide' : 'Read'} in {LANG[q.lang] || q.lang}
          </button>
          {showOriginal && <p className="translated-text fade">{q.text}</p>}
        </div>
      )}

      <div className="stack" style={{ '--gap': '8px', marginTop: 16 }}>
        <button className="btn btn-ok btn-lg btn-block" onClick={() => decide('approve')} disabled={!!busy}>
          {busy === 'approve' ? <Spinner /> : `Approve ${rupees(q.total)}`}
        </button>
        {confirmReject ? (
          <div className="row fade" style={{ '--gap': '8px' }}>
            <button className="btn btn-block" onClick={() => setConfirmReject(false)} disabled={!!busy}>Keep it</button>
            <button className="btn btn-block" style={{ color: 'var(--bad)' }} onClick={() => decide('reject')} disabled={!!busy}>
              {busy === 'reject' ? <Spinner /> : 'Yes, decline'}
            </button>
          </div>
        ) : (
          <button className="btn btn-ghost btn-block" onClick={() => setConfirmReject(true)} disabled={!!busy}>Decline</button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 12, textAlign: 'center' }}>
        {owner ? `${owner}, ` : ''}work above {rupees(q.quote_limit)} always waits for your OK.
      </p>
    </section>
  )
}

function Bill({ data, done }) {
  return (
    <section className={`card enter ${done ? 'bill-final' : ''}`} style={{ '--i': 3 }}>
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3>{done ? 'Final bill' : 'Bill so far'}</h3>
      </div>
      <dl className="lines">
        {data.parts.map((p, i) => (
          <div key={i} className="line"><dt>{p.name}{p.qty > 1 ? ` × ${p.qty}` : ''}</dt><dd className="num">{rupees(p.total)}</dd></div>
        ))}
        {data.labour > 0 && <div className="line"><dt>Labour</dt><dd className="num">{rupees(data.labour)}</dd></div>}
        <div className="line line-total"><dt>Total</dt><dd className="num"><CountUp value={data.bill} format={rupees} /></dd></div>
      </dl>
    </section>
  )
}

function CustomerSkeleton() {
  return (
    <main className="page customer stack" style={{ paddingTop: 72 }}>
      <Skeleton h={160} style={{ borderRadius: 24 }} />
      <Skeleton h={220} style={{ borderRadius: 24 }} />
    </main>
  )
}

const LANG = { mr: 'Marathi', hi: 'Hindi', gu: 'Gujarati', kn: 'Kannada', ta: 'Tamil', te: 'Telugu', bn: 'Bengali', ml: 'Malayalam', pa: 'Punjabi' }

function capitalise(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
