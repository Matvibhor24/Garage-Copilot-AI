// Owner > Today: the AI front desk's calls (C15). Price estimates wait here for the owner's OK before the caller
// gets them; callback requests stay until marked done; drop-off bookings and recent calls are listed.
import { useState } from 'react'
import { api, requestId } from '../data/api.js'
import { useLiveView } from '../data/live.js'
import { ago, clock, rupees } from '../format.js'
import { Skeleton, Spinner, useToast } from '../ui.jsx'

export default function OwnerCalls({ g }) {
  const view = useLiveView(() => api('/api/owner/calls'), {
    watch: [`garages/${g}/calls`, `garages/${g}/callbacks`, `garages/${g}/estimates`, `garages/${g}/bookings`],
  })
  const d = view.data
  if (!d) return <section className="card calls-card"><h2>Calls</h2><Skeleton h={120} /></section>
  const empty = !d.calls.length && !d.callbacks.length && !d.estimates.length && !d.bookings.length
  return (
    <section className="card calls-card" aria-label="Calls">
      <div className="row between" style={{ marginBottom: 10 }}>
        <h2>Calls</h2>
        <span className="muted small">AI front desk</span>
      </div>
      {empty && <div className="empty">No calls yet. Customers can call from their status page or the website.</div>}
      {d.estimates.map((e) => <EstimateAsk key={e.id} e={e} onDone={view.reload} />)}
      {d.callbacks.map((c) => <Callback key={c.id} c={c} onDone={view.reload} />)}
      {d.bookings.length > 0 && (
        <div className="calls-group">
          <h3 className="small muted">Drop-offs booked</h3>
          <ul className="calls-list">
            {d.bookings.map((b) => (
              <li key={b.id}><strong>{b.when}</strong> · {b.name || b.phone} · {b.vehicle || 'vehicle'}{b.note ? ` · ${b.note}` : ''}</li>
            ))}
          </ul>
        </div>
      )}
      {d.calls.length > 0 && (
        <div className="calls-group">
          <h3 className="small muted">Recent calls</h3>
          <ol className="calls-list">
            {d.calls.map((c) => (
              <li key={c.id} className="call-row">
                <div className="row between wrap" style={{ '--gap': '6px' }}>
                  <span><strong className="num">{c.phone}</strong> {c.verified ? <span className="chip chip-sm chip-ok">their own link</span> : <span className="chip chip-sm">website</span>}</span>
                  <span className="muted small num">{clock(c.started_at)}</span>
                </div>
                <p className="small">“{c.summary}”</p>
                {c.actions?.length > 0 && <p className="small muted">AI: {c.actions.join(' · ')}</p>}
              </li>
            ))}
          </ol>
        </div>
      )}
    </section>
  )
}

function EstimateAsk({ e, onDone }) {
  const toast = useToast()
  const [busy, setBusy] = useState('')
  async function answer(kind) {
    setBusy(kind)
    try {
      await api(`/api/owner/estimates/${e.id}/${kind}`, { method: 'POST', body: { request_id: requestId() } })
      toast(kind === 'send' ? `Estimate sent to ${e.name || e.phone}` : 'Estimate dropped')
      onDone()
    } catch (err) {
      toast(err.message)
    } finally {
      setBusy('')
    }
  }
  return (
    <div className="agent-ask card card-flat pop" role="status">
      <div className="grow stack" style={{ '--gap': '2px' }}>
        <span className="eyebrow" style={{ color: 'var(--accent)' }}>Price asked · {ago(e.at)}</span>
        <p style={{ fontWeight: 550 }}>{e.name || e.phone}: {e.work}{e.vehicle ? ` on a ${e.vehicle}` : ''}</p>
        <p className="small muted">{e.lines.map((l) => `${l.name} ${rupees(l.total)}`).join(' + ')}{e.labour ? ` + labour ${rupees(e.labour)}` : ''}{e.service_fee ? ` + service ${rupees(e.service_fee)}` : ''}</p>
      </div>
      <div className="row" style={{ '--gap': '8px' }}>
        <button className="btn btn-accent btn-sm" onClick={() => answer('send')} disabled={!!busy}>{busy === 'send' ? <Spinner /> : `Send ${rupees(e.total)}`}</button>
        <button className="btn btn-sm" onClick={() => answer('drop')} disabled={!!busy}>Drop</button>
      </div>
    </div>
  )
}

function Callback({ c, onDone }) {
  const toast = useToast()
  async function done() {
    try {
      await api(`/api/owner/callbacks/${c.id}/done`, { method: 'POST', body: { request_id: requestId() } })
      onDone()
    } catch (err) {
      toast(err.message)
    }
  }
  return (
    <div className="agent-ask card card-flat callback-row">
      <div className="grow stack" style={{ '--gap': '2px' }}>
        <span className="eyebrow" style={{ color: 'var(--warn)' }}>Call back · {ago(c.at)}</span>
        <p style={{ fontWeight: 550 }}>{c.name || 'Caller'} · <a href={`tel:${c.phone}`} className="num">{c.phone}</a></p>
        <p className="small muted">About {c.reason}</p>
      </div>
      <button className="btn btn-sm" onClick={done}>Done</button>
    </div>
  )
}
