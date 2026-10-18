// Owner records (C17): Jobs (transactions), Customers, Vehicles, Staff. Same look as the dashboard: cards, tables
// that become cards on phones, loading and empty states, ₹ with Indian digit grouping.
import { useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE, DEMO } from '../config.js'
import { apiUrl, api, requestId } from '../data/api.js'
import { idToken } from '../data/auth.js'
import { clock, minutes, plate, rupees, STAGE_LABEL } from '../format.js'
import { ErrorNote, Skeleton, Spinner, useToast } from '../ui.jsx'
import { Money } from '../vehicle3d/JobViewer.jsx'
import Vehicle3D from '../vehicle3d/Vehicle3D.jsx'

// ---------------------------------------------------------------- small pieces

function useFetch(path) {
  const [state, setState] = useState({ data: null, error: null })
  const [n, setN] = useState(0)
  useEffect(() => {
    let stale = false
    setState((s) => ({ data: s.data, error: null }))
    api(path).then((data) => !stale && setState({ data, error: null })).catch((error) => !stale && setState({ data: null, error }))
    return () => { stale = true }
  }, [path, n])
  return { ...state, reload: () => setN((x) => x + 1) }
}

const istToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
function shiftDays(ymd, n) {
  const d = new Date(`${ymd}T12:00:00+05:30`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}
function rangeFor(range, custom) {
  const today = istToday()
  if (range === 'today') return [today, today]
  if (range === 'week') {
    const dow = (new Date(`${today}T12:00:00+05:30`).getUTCDay() + 6) % 7
    return [shiftDays(today, -dow), today]
  }
  if (range === 'month') return [`${today.slice(0, 8)}01`, today]
  if (range === 'custom') return [custom.from, custom.to]
  return ['', '']
}
const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== '' && v != null)).toString()

function Dialog({ title, sub, onClose, children, wide }) {
  const ref = useRef(null)
  useEffect(() => { ref.current?.showModal() }, [])
  return (
    <dialog ref={ref} className={`v3d-dialog rec-dialog ${wide ? 'rec-wide' : ''}`} onClose={onClose}
      onClick={(e) => e.target === ref.current && ref.current.close()} aria-label={title}>
      <div className="v3d-dialog-body">
        <div className="row between">
          <div className="stack" style={{ '--gap': '2px' }}>
            {sub && <span className="muted small">{sub}</span>}
            <h2>{title}</h2>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => ref.current.close()} autoFocus>Close</button>
        </div>
        {children}
      </div>
    </dialog>
  )
}

function Search({ value, onChange, label }) {
  return <input className="input grow rec-search" type="search" placeholder={label} aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} />
}

function Seg({ value, options, onChange, label }) {
  return (
    <div className="seg" role="group" aria-label={label}>
      {options.map(([k, text]) => <button key={k} className={value === k ? 'on' : ''} aria-pressed={value === k} onClick={() => onChange(k)}>{text}</button>)}
    </div>
  )
}

function Stat({ label, value }) {
  return <div className="rec-stat"><span className="muted small">{label}</span><strong className="num">{value}</strong></div>
}

function Empty({ children }) {
  return <div className="empty">{children}</div>
}

// ---------------------------------------------------------------- Jobs

export function Jobs() {
  const toast = useToast()
  const [range, setRange] = useState('month')
  const [custom, setCustom] = useState({ from: shiftDays(istToday(), -30), to: istToday() })
  const [status, setStatus] = useState('')
  const [mechanic, setMechanic] = useState('')
  const [q, setQ] = useState('')
  const [more, setMore] = useState([])
  const [cursor, setCursor] = useState('')
  const [open, setOpen] = useState(null)
  const [from, to] = rangeFor(range, custom)
  const filter = { from, to, status, mechanic, q: q.trim() }
  const page = useFetch(`/api/owner/jobs?${qs(filter)}`)
  const staff = useFetch('/api/owner/staff?period=month')
  useEffect(() => { setMore([]); setCursor(page.data?.next_cursor || '') }, [page.data])

  async function loadMore() {
    try {
      const next = await api(`/api/owner/jobs?${qs({ ...filter, cursor })}`)
      setMore((m) => [...m, ...next.jobs])
      setCursor(next.next_cursor)
    } catch (e) {
      toast(e.message)
    }
  }

  async function exportCsv() {
    try {
      const path = `/api/owner/jobs.csv?${qs(filter)}`
      let text
      if (DEMO) text = await api(path)
      else {
        const res = await fetch(API_BASE + path, { headers: { Authorization: `Bearer ${await idToken()}` } })
        if (!res.ok) throw new Error(`Export failed (${res.status})`)
        text = await res.text()
      }
      const url = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
      const a = Object.assign(document.createElement('a'), { href: url, download: `garage-jobs${from ? `-${from}` : ''}${to ? `-to-${to}` : ''}.csv` })
      document.body.append(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (e) {
      toast(e.message)
    }
  }

  const rows = [...(page.data?.jobs || []), ...more]
  const t = page.data?.totals
  return (
    <section className="card rec enter" aria-label="Jobs">
      <div className="rec-filters">
        <Seg label="Dates" value={range} onChange={setRange} options={[['today', 'Today'], ['week', 'This week'], ['month', 'This month'], ['all', 'All'], ['custom', 'Dates']]} />
        {range === 'custom' && (
          <div className="row wrap" style={{ '--gap': '6px' }}>
            <input className="input" type="date" aria-label="From" value={custom.from} onChange={(e) => setCustom({ ...custom, from: e.target.value })} />
            <input className="input" type="date" aria-label="To" value={custom.to} onChange={(e) => setCustom({ ...custom, to: e.target.value })} />
          </div>
        )}
        <Seg label="Status" value={status} onChange={setStatus} options={[['', 'All'], ['open', 'Open'], ['closed', 'Closed']]} />
        <select className="input rec-select" aria-label="Mechanic" value={mechanic} onChange={(e) => setMechanic(e.target.value)}>
          <option value="">All mechanics</option>
          {(staff.data?.mechanics || []).map((m) => <option key={m.uid} value={m.name}>{m.name}</option>)}
        </select>
        <Search value={q} onChange={setQ} label="Search plate, customer or job" />
        <button className="btn" onClick={exportCsv} disabled={!rows.length}>Export CSV</button>
      </div>

      <ErrorNote error={page.error} onRetry={page.reload} />
      {t && (
        <div className="rec-stats" aria-label="Totals for this filter">
          <Stat label="Jobs" value={t.jobs} />
          <Stat label="Revenue" value={rupees(t.revenue)} />
          <Stat label="Average bill" value={rupees(t.average_bill)} />
          <Stat label="Average time" value={minutes(t.average_minutes) || '—'} />
          <Stat label="Margin" value={rupees(t.margin)} />
        </div>
      )}

      {!page.data && !page.error ? <Skeleton h={320} /> : rows.length === 0 ? <Empty>No jobs match.</Empty> : (
        <table className="rec-table">
          <thead><tr><th>Date</th><th>Job</th><th>Vehicle</th><th>Customer</th><th>Mechanic</th><th>Status</th><th className="num">Bill</th><th className="num">Time</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.job_id} tabIndex={0} onClick={() => setOpen(r.job_id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setOpen(r.job_id))} aria-label={`Open ${r.job_id}`}>
                <td data-label="Date">{r.date}</td>
                <td data-label="Job" className="mono">{r.job_id}</td>
                <td data-label="Vehicle"><strong>{r.vehicle}</strong> <span className="muted small">{plate(r.plate)}</span></td>
                <td data-label="Customer">{r.customer}</td>
                <td data-label="Mechanic">{r.mechanic || '—'}</td>
                <td data-label="Status"><span className={`chip chip-sm ${r.status === 'closed' ? 'chip-ok' : 'chip-accent'}`}>{r.status === 'closed' ? 'Closed' : STAGE_LABEL[r.stage] || 'Open'}</span></td>
                <td data-label="Bill" className="num" title={`Service ${rupees(r.service || 0)} + parts ${rupees(r.parts)} + consumables ${rupees(r.consumables)} + labour ${rupees(r.labour)}`}>
                  {rupees(r.bill)}{r.bill > 0 && <span className="muted small rec-split">{r.service ? `${rupees(r.service)} + ` : ''}{rupees(r.parts)} + {rupees(r.consumables)} + {rupees(r.labour)}</span>}
                </td>
                <td data-label="Time" className="num">{minutes(r.minutes) || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {cursor && <button className="btn btn-block" onClick={loadMore}>Show more</button>}
      {open && <JobDetail id={open} onClose={() => setOpen(null)} />}
    </section>
  )
}

export function JobDetail({ id, onClose }) {
  const d = useFetch(`/api/owner/jobs/${id}`)
  const j = d.data
  return (
    <Dialog title={j ? `${j.vehicle} · ${plate(j.plate)}` : id} sub={j ? `${id} · ${j.owner} · ${j.mechanic_name || 'no mechanic'}` : ''} onClose={onClose} wide>
      {!j ? (d.error ? <ErrorNote error={d.error} onRetry={d.reload} /> : <Skeleton h={300} />) : (
        <div className="rec-detail">
          <div className="stack" style={{ '--gap': '12px' }}>
            <Vehicle3D job={j} compact caption={false} />
            <Money m={j.money} done={j.status === 'done'} />
            {j.photos?.length > 0 && <div className="rec-photos">{j.photos.map((p) => <img key={p.path} src={apiUrl(p.url)} alt={`Photo on ${id}`} />)}</div>}
          </div>
          <div className="stack" style={{ '--gap': '14px' }}>
            <div>
              <h3 className="rec-h3">Timeline · {minutes(j.minutes)}</h3>
              <ol className="rec-timeline">
                {j.timeline.map((s, i) => <li key={i}><span>{s.label}</span><span className="muted small num">{clock(s.started_at)}{s.minutes != null ? ` · ${minutes(s.minutes)}` : ''}</span></li>)}
                {!j.timeline.length && <li className="muted small">Stage times are kept for jobs opened with the voice agent.</li>}
              </ol>
            </div>
            <div>
              <h3 className="rec-h3">Parts</h3>
              {j.parts?.length ? <ul className="rec-lines">{j.parts.map((p, i) => <li key={i}><span>{p.name}{p.qty > 1 ? ` × ${p.qty}` : ''}{p.consumable ? <span className="muted small"> · consumable</span> : ''}</span><span className="num">{rupees(p.total)}</span></li>)}</ul> : <p className="muted small">No parts.</p>}
              {j.consumables?.length > 0 && <p className="muted small">Garage's own fittings: {j.consumables.map((c) => `${c.name} × ${c.qty}`).join(', ')}</p>}
            </div>
            <div>
              <h3 className="rec-h3">Quotes</h3>
              {j.quotes?.length ? <ul className="rec-lines">{j.quotes.map((q) => <li key={q.id}><span className="mono">{q.id}</span><span>{rupees(q.total)} · {q.status === 'approved' ? (q.auto ? 'approved automatically' : 'approved by the customer') : q.status === 'rejected' ? 'declined' : q.status}</span></li>)}</ul> : <p className="muted small">No quotes.</p>}
            </div>
            <div>
              <h3 className="rec-h3">Messages sent</h3>
              {j.messages?.length ? <ul className="rec-msgs">{j.messages.map((m, i) => <li key={i}><span className="muted small">{clock(m.at)} · {m.kind?.replaceAll('_', ' ')}</span><span className="small">{m.text}</span></li>)}</ul> : <p className="muted small">No messages.</p>}
            </div>
          </div>
        </div>
      )}
    </Dialog>
  )
}

// ---------------------------------------------------------------- Customers

const LANG = { en: 'English', hi: 'Hindi', mr: 'Marathi', gu: 'Gujarati', kn: 'Kannada', ta: 'Tamil', te: 'Telugu', bn: 'Bengali', ml: 'Malayalam', pa: 'Punjabi' }

export function Customers() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const list = useFetch(`/api/owner/customers?${qs({ q: q.trim() })}`)
  return (
    <section className="card rec enter" aria-label="Customers">
      <div className="rec-filters"><Search value={q} onChange={setQ} label="Search name, phone or plate" /></div>
      <ErrorNote error={list.error} onRetry={list.reload} />
      {!list.data && !list.error ? <Skeleton h={300} /> : !list.data?.length ? <Empty>No customers match.</Empty> : (
        <table className="rec-table">
          <thead><tr><th>Name</th><th>Phone</th><th>Language</th><th>Vehicles</th><th className="num">Visits</th><th className="num">Total spent</th><th>Last visit</th></tr></thead>
          <tbody>
            {list.data.map((c) => (
              <tr key={c.id} tabIndex={0} onClick={() => setOpen(c.id)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setOpen(c.id))} aria-label={`Open ${c.name}`}>
                <td data-label="Name"><strong>{c.name}</strong>{c.open_jobs.length > 0 && <span className="chip chip-sm chip-accent" style={{ marginLeft: 6 }}>in now</span>}</td>
                <td data-label="Phone" className="num">{c.phone || '—'}</td>
                <td data-label="Language">{LANG[c.lang] || c.lang}</td>
                <td data-label="Vehicles" className="small">{c.vehicles.map((v) => v.replace(/ · (\w+)$/, (_, p) => ` · ${plate(p)}`)).join(', ')}</td>
                <td data-label="Visits" className="num">{c.visits}</td>
                <td data-label="Total spent" className="num">{rupees(c.total_spent)}</td>
                <td data-label="Last visit">{c.last_visit}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && <CustomerDetail id={open} onClose={() => setOpen(null)} />}
    </section>
  )
}

function CustomerDetail({ id, onClose }) {
  const toast = useToast()
  const d = useFetch(`/api/owner/customers/${encodeURIComponent(id)}`)
  const [job, setJob] = useState(null)
  const c = d.data
  async function sendLink(jobId) {
    try {
      await api(`/api/owner/jobs/${jobId}/status-link`, { method: 'POST', body: { request_id: requestId() } })
      toast(`Status link sent to ${c.name}`)
    } catch (e) {
      toast(e.message)
    }
  }
  return (
    <Dialog title={c?.name || 'Customer'} sub={c ? `${c.phone || 'no phone'} · ${LANG[c.lang] || c.lang}` : ''} onClose={onClose}>
      {!c ? <Skeleton h={200} /> : (
        <div className="stack" style={{ '--gap': '12px' }}>
          <div className="rec-stats"><Stat label="Visits" value={c.visits} /><Stat label="Total spent" value={rupees(c.total_spent)} /><Stat label="Last visit" value={c.last_visit || '—'} /></div>
          <p className="small"><span className="muted">Vehicles: </span>{c.vehicles.join(', ')}</p>
          <ul className="rec-lines">
            {c.jobs.map((r) => (
              <li key={r.job_id}>
                <button className="link-btn" onClick={() => setJob(r.job_id)}>{r.date} · {r.job_id} · {r.vehicle}</button>
                <span className="row" style={{ '--gap': '8px' }}>
                  <span className="num">{r.status === 'closed' ? rupees(r.bill) : STAGE_LABEL[r.stage]}</span>
                  {r.status === 'open' && <button className="btn btn-sm btn-accent" onClick={() => sendLink(r.job_id)}>Send status link</button>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {job && <JobDetail id={job} onClose={() => setJob(null)} />}
    </Dialog>
  )
}

// ---------------------------------------------------------------- Vehicles

export function Vehicles() {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(null)
  const list = useFetch(`/api/owner/vehicles?${qs({ q: q.trim() })}`)
  return (
    <section className="card rec enter" aria-label="Vehicles">
      <div className="rec-filters"><Search value={q} onChange={setQ} label="Search plate, model or owner" /></div>
      <ErrorNote error={list.error} onRetry={list.reload} />
      {!list.data && !list.error ? <Skeleton h={300} /> : !list.data?.length ? <Empty>No vehicles match.</Empty> : (
        <table className="rec-table">
          <thead><tr><th>Plate</th><th>Model</th><th>Owner</th><th className="num">Visits</th><th>Last service</th><th className="num">Total spent</th></tr></thead>
          <tbody>
            {list.data.map((v) => (
              <tr key={v.plate} tabIndex={0} onClick={() => setOpen(v.plate)} onKeyDown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), setOpen(v.plate))} aria-label={`Open ${v.plate}`}>
                <td data-label="Plate" className="mono">{plate(v.plate)}{v.in_now && <span className="chip chip-sm chip-accent" style={{ marginLeft: 6 }}>in now</span>}</td>
                <td data-label="Model"><strong>{v.vehicle}</strong></td>
                <td data-label="Owner">{v.owner}</td>
                <td data-label="Visits" className="num">{v.visits}</td>
                <td data-label="Last service">{v.last_visit} <span className="muted small">{v.last_work}{v.last_parts.length ? ` · ${v.last_parts.join(', ')}` : ''}</span></td>
                <td data-label="Total spent" className="num">{rupees(v.total_spent)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {open && <VehicleDetail plateNo={open} onClose={() => setOpen(null)} />}
    </section>
  )
}

function VehicleDetail({ plateNo, onClose }) {
  const d = useFetch(`/api/owner/vehicles/${encodeURIComponent(plateNo)}`)
  const [job, setJob] = useState(null)
  const v = d.data
  return (
    <Dialog title={v ? `${v.vehicle} · ${plate(v.plate)}` : plate(plateNo)} sub={v ? `${v.owner} · ${v.visits} visit${v.visits === 1 ? '' : 's'} · ${rupees(v.total_spent)} spent` : ''} onClose={onClose}>
      {!v ? <Skeleton h={200} /> : (
        <ol className="rec-history">
          {v.history.map((h) => (
            <li key={h.job_id}>
              <div className="row between wrap"><button className="link-btn" onClick={() => setJob(h.job_id)}>{h.date} · {h.job_id}</button><span className="num">{h.status === 'closed' ? rupees(h.bill) : 'in now'}</span></div>
              <span className="small">{h.complaint || '—'}</span>
              {h.parts_fitted.length > 0 && <span className="muted small">{h.parts_fitted.join(', ')}</span>}
            </li>
          ))}
        </ol>
      )}
      {job && <JobDetail id={job} onClose={() => setJob(null)} />}
    </Dialog>
  )
}

// ---------------------------------------------------------------- Staff

export function Staff() {
  const toast = useToast()
  const [period, setPeriod] = useState('week')
  const s = useFetch(`/api/owner/staff?period=${period}`)
  const [form, setForm] = useState({ name: '', phone: '', pin: '' })
  const [busy, setBusy] = useState(false)
  const max = useMemo(() => Math.max(1, ...(s.data?.mechanics || []).flatMap((m) => m.per_day.map((d) => d.jobs))), [s.data])

  async function add(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const out = await api('/api/owner/mechanics', { method: 'POST', body: { ...form, request_id: requestId() } })
      toast(`${out.name} added${out.has_pin ? ' with a PIN' : ''}`)
      setForm({ name: '', phone: '', pin: '' })
      s.reload()
    } catch (err) {
      toast(err.message)
    } finally {
      setBusy(false)
    }
  }
  async function setActive(m, active) {
    if (!active && !window.confirm(`Switch off ${m.name}? They can no longer sign in. Their history stays.`)) return
    try {
      await api(`/api/owner/mechanics/${m.uid}/${active ? 'reactivate' : 'deactivate'}`, { method: 'POST', body: { request_id: requestId() } })
      toast(active ? `${m.name} can sign in again` : `${m.name} switched off`)
      s.reload()
    } catch (err) {
      toast(err.message)
    }
  }

  const label = { today: 'today', week: 'this week', month: 'this month' }[period]
  return (
    <section className="stack enter" style={{ '--gap': '16px' }} aria-label="Staff">
      <div className="row between wrap">
        <h2>{s.data ? `${s.data.count} mechanic${s.data.count === 1 ? '' : 's'}` : 'Staff'}</h2>
        <Seg label="Period" value={period} onChange={setPeriod} options={[['today', 'Today'], ['week', 'This week'], ['month', 'This month']]} />
      </div>
      <ErrorNote error={s.error} onRetry={s.reload} />
      {!s.data ? <Skeleton h={260} /> : !s.data.mechanics.length ? <Empty>No mechanics yet. Add one below.</Empty> : (
        <div className="staff-grid">
          {s.data.mechanics.map((m) => (
            <article key={m.uid} className={`card staff-card ${m.active ? '' : 'staff-off'}`} aria-label={m.name}>
              <div className="row between">
                <div className="stack" style={{ '--gap': '0px' }}>
                  <strong>{m.name}</strong>
                  <span className="muted small">{m.phone || 'PIN sign-in'} · last active {m.last_active ? `${new Date(m.last_active).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', timeZone: 'Asia/Kolkata' })}, ${clock(m.last_active)}` : '—'}</span>
                </div>
                {m.active ? <span className="chip chip-sm chip-ok">Active</span> : <span className="chip chip-sm">Switched off</span>}
              </div>
              <div className="rec-stats rec-stats-tight">
                <Stat label="Finished today" value={m.finished.today} />
                <Stat label="This week" value={m.finished.week} />
                <Stat label="This month" value={m.finished.month} />
                <Stat label="Open now" value={m.open_now} />
                <Stat label={`Avg time ${label}`} value={minutes(m.average_minutes) || '—'} />
                <Stat label={`Revenue ${label}`} value={rupees(m.revenue)} />
                <Stat label={`Parts ${label}`} value={m.parts_logged} />
              </div>
              <Bars days={m.per_day} max={max} name={m.name} />
              <button className="btn btn-sm btn-ghost" onClick={() => setActive(m, !m.active)}>{m.active ? 'Switch off' : 'Let them sign in again'}</button>
            </article>
          ))}
        </div>
      )}
      <form className="card rec-add" onSubmit={add} aria-label="Add mechanic">
        <h3>Add mechanic</h3>
        <div className="row wrap" style={{ '--gap': '8px' }}>
          <input className="input grow" placeholder="Name" aria-label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          <input className="input grow" placeholder="Phone (for OTP sign-in)" aria-label="Phone" inputMode="tel" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
          <input className="input" placeholder="PIN" aria-label="PIN" inputMode="numeric" maxLength={6} value={form.pin} onChange={(e) => setForm({ ...form, pin: e.target.value.replace(/\D/g, '') })} style={{ width: 100 }} />
          <button className="btn btn-primary" disabled={busy || !form.name.trim()}>{busy ? <Spinner /> : 'Add'}</button>
        </div>
        <p className="muted small">A name and PIN lets them sign in on the shared garage phone; a phone number lets them use OTP on their own phone.</p>
      </form>
    </section>
  )
}

// Jobs finished per day: one series, so one colour and no legend; a value on hover, and the numbers as text too.
function Bars({ days, max, name }) {
  const total = days.reduce((t, d) => t + d.jobs, 0)
  return (
    <figure className="bars" aria-label={`${name}: jobs finished per day, ${total} in total`}>
      <div className="bars-plot" role="list">
        {days.map((d) => (
          <div key={d.day} className="bar-slot" role="listitem" tabIndex={0} aria-label={`${d.day}: ${d.jobs} job${d.jobs === 1 ? '' : 's'}`} data-tip={`${d.day.slice(5)} · ${d.jobs}`}>
            <span className="bar" style={{ height: `${(d.jobs / max) * 100}%` }} />
          </div>
        ))}
      </div>
      <figcaption className="muted small">Jobs finished per day · {total} in total</figcaption>
    </figure>
  )
}
