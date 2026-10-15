// The customer's page: /j/:token. No login. Live status, the quote with its photo, one-tap approval.
// English by default with an English | हिंदी switch (C12); every string comes from src/i18n.js.
import { useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../data/api.js'
import { customerFirestore } from '../data/auth.js'
import { useLiveView } from '../data/live.js'
import { clock, minutes, plate, rupees } from '../format.js'
import { LANGS, t, textIn, useCustomerLang } from '../i18n.js'
import { Check, CountUp, ErrorNote, LiveBadge, Skeleton, Spinner, useToast } from '../ui.jsx'
import Vehicle3D from '../vehicle3d/Vehicle3D.jsx'
import { CallButton } from './CallPanel.jsx'

const STEPS = ['intake', 'service', 'washing', 'ready']

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
  const [lang, setLang] = useCustomerLang()
  const tr = (key, vars) => t(lang, key, vars)
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
        <div className="row" style={{ justifyContent: 'flex-end' }}><LangSwitch lang={lang} onChange={setLang} /></div>
        <h1>{tr('linkBroken')}</h1>
        <p className="muted">{error?.status === 403 ? tr('linkExpired') : lang === 'en' ? error?.message : tr('error')}</p>
      </main>
    )
  }

  const done = data.status === 'done'
  const pending = data.quotes.filter((q) => q.status === 'pending')
  const decided = data.quotes.filter((q) => q.status !== 'pending' && q.status !== 'draft')
  const stageTitle = done ? tr('stage.ready') : tr(`stage.${data.stage}`) || data.stage_label

  return (
    <main className="page customer stack" style={{ '--gap': '16px' }} lang={lang}>
      <header className="topbar">
        <div className="stack" style={{ '--gap': '0px' }}>
          <span className="garage-name">{data.garage}</span>
          <span className="muted small">{tr('job', { id: data.job_id })}</span>
        </div>
        <div className="row" style={{ '--gap': '8px' }}>
          <LangSwitch lang={lang} onChange={setLang} />
          <LiveBadge label={tr('live')} />
        </div>
      </header>

      <ErrorNote error={error} onRetry={reload} />

      {/* Phones: one column. Wide screens: the vehicle and status stay on the left, the rest on the right. */}
      <div className="customer-grid">
        <div className="customer-main">
          <section className={`card hero enter ${done ? 'hero-done' : ''}`}>
            <div className="row between wrap">
              <div className="stack" style={{ '--gap': '6px' }}>
                <span className="eyebrow">{tr('yourVehicle')}</span>
                <h2 style={{ fontSize: 24 }}>{data.vehicle}</h2>
              </div>
              <span className="plate mono">{plate(data.plate)}</span>
            </div>
            <Vehicle3D job={data} caption={false} />
            <div className="hero-status">
              {done ? <Check size={44} /> : <span className="status-pulse" aria-hidden="true" />}
              <div className="stack" style={{ '--gap': '2px' }}>
                <h1 className="status-title" key={stageTitle}>{stageTitle}</h1>
                <span className="muted small">{done ? tr('finalBillAmount', { amount: rupees(data.bill) }) : statusHint(data, tr)}</span>
              </div>
            </div>
          </section>
        </div>

        <div className="customer-side stack" style={{ '--gap': '16px' }}>
          {pending.map((q) => <QuoteCard key={q.id} q={q} token={token} owner={data.owner} onDone={reload} lang={lang} />)}

          <section className="card enter" style={{ '--i': 1 }}>
            <h3 style={{ marginBottom: 12 }}>{tr('progress')}</h3>
            <Timeline data={data} tr={tr} />
          </section>

          {decided.map((q, i) => (
            <section key={q.id} className="card card-flat row between enter" style={{ '--i': 2 + i }}>
              <div className="stack" style={{ '--gap': '2px' }}>
                <h3>{tr('quote', { id: q.id })}</h3>
                <span className="muted small">{tr('plusLabour', { parts: q.lines.map((l) => l.name).join(', ') })}</span>
              </div>
              <div className="stack" style={{ '--gap': '4px', alignItems: 'flex-end' }}>
                <span className="num" style={{ fontWeight: 650 }}>{rupees(q.total)}</span>
                <span className={`chip ${q.status === 'approved' ? 'chip-ok' : 'chip-bad'}`}>{q.status === 'approved' ? (q.auto ? tr('approvedAuto') : tr('approved')) : tr('declined')}</span>
                {q.auto && <span className="muted small">{tr('withinLimit', { amount: rupees(q.quote_limit) })}</span>}
              </div>
            </section>
          ))}

          {(done || data.parts.length > 0) && <Bill data={data} done={done} tr={tr} />}
          {data.messages?.length > 0 && <Messages messages={data.messages} lang={lang} tr={tr} />}
        </div>
      </div>

      <div className="center stack" style={{ '--gap': '8px', paddingTop: 8 }}>
        <CallButton className="btn" label={tr('callGarage')} garage={data.garage}
          getToken={async () => (await api(`/api/j/${token}/call`, { method: 'POST', anonymous: true })).token} />
        <p className="muted small" style={{ textAlign: 'center' }}>{tr('updatesItself')}</p>
      </div>
    </main>
  )
}

// English | हिंदी, visible in the header.
function LangSwitch({ lang, onChange }) {
  return (
    <div className="seg lang-switch" role="group" aria-label={t(lang, 'language')}>
      {Object.entries(LANGS).map(([code, label]) => (
        <button key={code} className={lang === code ? 'on' : ''} aria-pressed={lang === code} lang={code} onClick={() => onChange(code)}>{label}</button>
      ))}
    </div>
  )
}

function statusHint(data, tr) {
  const last = data.timeline[data.timeline.length - 1]
  if (data.quotes.some((q) => q.status === 'pending')) return tr('waitingForOk')
  return last ? tr('since', { time: clock(last.started_at) }) : ''
}

function Timeline({ data, tr }) {
  const at = {}
  for (const s of data.timeline) if (!at[s.name]) at[s.name] = s
  if (at.done && !at.ready) at.ready = at.done
  const stageKey = data.stage === 'done' ? 'ready' : data.stage === 'waiting_approval' ? 'service' : data.stage
  const current = Math.max(0, STEPS.indexOf(stageKey))
  const doneAll = data.status === 'done'
  return (
    <ol className="timeline" style={{ '--progress': doneAll ? 1 : current / (STEPS.length - 1) }}>
      {STEPS.map((key, i) => {
        const state = doneAll || i < current ? 'done' : i === current ? 'now' : 'todo'
        const step = at[key]
        return (
          <li key={key} className={`tl-step tl-${state}`}>
            <span className="tl-dot" aria-hidden="true">{state === 'done' && <svg width="12" height="12" viewBox="0 0 12 12"><path d="M2.5 6.2 5 8.5l4.5-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}</span>
            <span className="grow">{tr(`stage.${key}`)}</span>
            <span className="muted small num">
              {state === 'now' && !doneAll ? <span className="chip chip-accent">{tr('now')}</span> : step ? (step.minutes != null && key !== 'ready' ? minutes(step.minutes) : clock(step.started_at)) : ''}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function QuoteCard({ q, token, owner, onDone, lang }) {
  const toast = useToast()
  const tr = (key, vars) => t(lang, key, vars)
  const [busy, setBusy] = useState('')
  const [result, setResult] = useState(null)
  const [confirmReject, setConfirmReject] = useState(false)
  const [showText, setShowText] = useState(false)
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
      else toast(lang === 'en' ? e.message : tr('error'))
    } finally {
      setBusy('')
    }
  }

  if (result) {
    return (
      <section className="card quote-done pop center stack" style={{ '--gap': '10px', textAlign: 'center' }}>
        {result === 'approved' ? <Check size={64} /> : <span className="decline-mark">✕</span>}
        <h2>{result === 'approved' ? tr('approved') : tr('declined')}</h2>
        <p className="muted">{result === 'approved' ? tr('approvedThanks') : tr('declinedOk')}</p>
      </section>
    )
  }

  const message = textIn(lang, q)
  return (
    <section className="card quote enter" aria-labelledby={`q-${q.id}`}>
      <div className="row between">
        <span className="chip chip-accent"><span className="dot live-dot" />{tr('approvalNeeded')}</span>
        <span className="muted small">{tr('quote', { id: q.id })}</span>
      </div>

      <h2 id={`q-${q.id}`} style={{ margin: '14px 0 4px' }}>{tr('extraWork')}</h2>
      {q.note && <p className="muted">{capitalise(q.note)}.</p>}

      {q.photo_url && (
        <figure className="quote-photo">
          <img src={q.photo_url} alt={q.photo_caption || tr('photoAlt')} />
          {q.photo_caption && <figcaption>“{q.photo_caption}”</figcaption>}
        </figure>
      )}

      <dl className="lines">
        {q.lines.map((l) => (
          <div key={l.part_id} className="line"><dt>{l.name}{l.qty > 1 ? ` × ${l.qty}` : ''}</dt><dd className="num">{rupees(l.total)}</dd></div>
        ))}
        <div className="line"><dt>{tr('labour')}</dt><dd className="num">{rupees(q.labour)}</dd></div>
        <div className="line line-total"><dt>{tr('total')}</dt><dd className="num"><CountUp value={q.total} format={rupees} /></dd></div>
      </dl>

      {message && (
        <div className="translated">
          <button className="link-btn" onClick={() => setShowText((v) => !v)} aria-expanded={showText}>
            {showText ? tr('hideMessage') : tr('readMessage')}
          </button>
          {showText && <p className="translated-text fade">{message}</p>}
        </div>
      )}

      <div className="stack" style={{ '--gap': '8px', marginTop: 16 }}>
        <button className="btn btn-ok btn-lg btn-block" onClick={() => decide('approve')} disabled={!!busy}>
          {busy === 'approve' ? <Spinner /> : tr('approveAmount', { amount: rupees(q.total) })}
        </button>
        {confirmReject ? (
          <div className="row fade" style={{ '--gap': '8px' }}>
            <button className="btn btn-block" onClick={() => setConfirmReject(false)} disabled={!!busy}>{tr('keepIt')}</button>
            <button className="btn btn-block" style={{ color: 'var(--bad)' }} onClick={() => decide('reject')} disabled={!!busy}>
              {busy === 'reject' ? <Spinner /> : tr('yesDecline')}
            </button>
          </div>
        ) : (
          <button className="btn btn-ghost btn-block" onClick={() => setConfirmReject(true)} disabled={!!busy}>{tr('decline')}</button>
        )}
      </div>
      <p className="muted small" style={{ marginTop: 12, textAlign: 'center' }}>
        {tr('limitNote', { owner: owner ? `${owner}, ` : '', amount: rupees(q.quote_limit) })}
      </p>
    </section>
  )
}

function Bill({ data, done, tr }) {
  return (
    <section className={`card enter ${done ? 'bill-final' : ''}`} style={{ '--i': 3 }}>
      <div className="row between" style={{ marginBottom: 8 }}>
        <h3>{done ? tr('finalBill') : tr('billSoFar')}</h3>
      </div>
      <dl className="lines">
        {data.parts.map((p, i) => (
          <div key={i} className="line"><dt>{p.name}{p.qty > 1 ? ` × ${p.qty}` : ''}</dt><dd className="num">{rupees(p.total)}</dd></div>
        ))}
        {data.labour > 0 && <div className="line"><dt>{tr('labour')}</dt><dd className="num">{rupees(data.labour)}</dd></div>}
        <div className="line line-total"><dt>{tr('total')}</dt><dd className="num"><CountUp value={data.bill} format={rupees} /></dd></div>
      </dl>
    </section>
  )
}

// What the garage sent this customer (WhatsApp), in the page's language.
function Messages({ messages, lang, tr }) {
  return (
    <section className="card card-flat enter messages-card" style={{ '--i': 4 }}>
      <h3 style={{ marginBottom: 10 }}>{tr('messages')}</h3>
      <ol className="cust-messages">
        {[...messages].reverse().map((m, i) => (
          <li key={`${m.at}-${i}`}>
            <div className="row between small muted"><span>{STRINGS_KIND.includes(m.kind) ? tr(`kind.${m.kind}`) : tr('kind.other')}</span><span className="num">{clock(m.at)}</span></div>
            <p className="msg-text">{textIn(lang, m).replace(/\s*https?:\/\/\S+/g, '')}</p>
          </li>
        ))}
      </ol>
    </section>
  )
}
const STRINGS_KIND = ['status_link', 'quote', 'final_bill']

function CustomerSkeleton() {
  return (
    <main className="page customer stack" style={{ paddingTop: 72 }}>
      <Skeleton h={160} style={{ borderRadius: 24 }} />
      <Skeleton h={220} style={{ borderRadius: 24 }} />
    </main>
  )
}

function capitalise(s) {
  return s ? s[0].toUpperCase() + s.slice(1) : s
}
