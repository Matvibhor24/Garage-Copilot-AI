// Demo backend: answers the same REST calls as the FastAPI service, from the in-browser store.
import { STAGE_LABEL } from '../format.js'
import * as store from './store.js'
import { GARAGE } from './store.js'
import * as records from './records.js'

export const subscribe = store.subscribe

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

class DemoError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export async function handle(method, fullPath, body = {}, rawBody) {
  await wait(180 + Math.random() * 160) // feel like a network
  const [path, qs] = fullPath.split('?')
  const query = new URLSearchParams(qs || '')
  const s = store.get()
  let m

  if ((m = path.match(/^\/api\/j\/demo-([^/]+)$/)) && method === 'GET') return customerView(s, m[1])
  if ((m = path.match(/^\/api\/j\/demo-([^/]+)\/quotes\/([^/]+)\/(approve|reject)$/))) {
    let out
    store.change((st) => { out = store.decideQuote(st, m[2], m[3] === 'approve' ? 'approved' : 'rejected') })
    return out
  }
  if ((m = path.match(/^\/api\/j\/demo-([^/]+)\/call$/)) && method === 'POST') return startCall(true)
  if (path.startsWith('/api/j/')) throw new DemoError(403, 'This link is invalid or has expired.')
  if (path === '/api/call/start' && method === 'POST') {
    if ((body.phone || '').replace(/\D/g, '').length < 10) throw new DemoError(409, 'say a 10-digit phone number')
    return startCall(false, body.phone)
  }

  if (path === '/api/auth/pin') {
    const person = (s.mechanics || []).find((x) => x.name.toLowerCase() === body.name.trim().toLowerCase())
    const ok = body.garage_id === GARAGE.id && person && body.pin === (person.pin || '1234')
    if (!ok) throw new DemoError(401, 'Wrong name or PIN')
    if (person.active === false) throw new DemoError(401, 'this account is switched off; ask the owner')
    const name = body.name.trim()[0].toUpperCase() + body.name.trim().slice(1).toLowerCase()
    return { claims: { garage: GARAGE.id, role: 'mechanic', name }, dev_token: `demo:${name}` }
  }

  if (path === '/api/jobs' && method === 'GET') return Object.values(s.jobs).filter((j) => j.status === 'open').map(compactJob)
  if (path === '/api/owner/dashboard') return dashboard(s)
  if (path === '/api/owner/inventory') {
    const all = Object.values(s.inventory)
    return query.get('low_only') === 'true' ? all.filter((p) => p.low_stock) : all
  }
  if (path === '/api/owner/audit') return s.audit.slice(0, Number(query.get('limit') || 50))
  if ((m = path.match(/^\/api\/owner\/inventory\/([^/]+)\/(restock|reorder|reorder-later)$/))) return ownerStock(m[1], m[2], body)
  if (path === '/api/owner/calls') return callsOverview(s)
  // Owner records (C17)
  const filter = { from: query.get('from') || '', to: query.get('to') || '', status: query.get('status') || '', mechanic: query.get('mechanic') || '', q: query.get('q') || '' }
  if (path === '/api/owner/jobs' && method === 'GET') return records.jobsPage(s, filter, query.get('cursor') || '')
  if (path === '/api/owner/jobs.csv') return records.jobsCsv(s, filter)
  if ((m = path.match(/^\/api\/owner\/jobs\/([^/]+)\/status-link$/))) return resendLink(m[1])
  if ((m = path.match(/^\/api\/owner\/jobs\/([^/]+)$/))) return records.jobDetail(s, m[1], STAGE_LABEL) || notFound()
  if (path === '/api/owner/customers') return records.customers(s, query.get('q') || '')
  if ((m = path.match(/^\/api\/owner\/customers\/([^/]+)$/))) return records.customerDetail(s, decodeURIComponent(m[1])) || notFound()
  if (path === '/api/owner/vehicles') return records.vehicles(s, query.get('q') || '')
  if ((m = path.match(/^\/api\/owner\/vehicles\/([^/]+)$/))) return records.vehicleDetail(s, decodeURIComponent(m[1])) || notFound()
  if (path === '/api/owner/staff') return records.staff(s, query.get('period') || 'week')
  if ((m = path.match(/^\/api\/owner\/mechanics\/([^/]+)\/(deactivate|reactivate)$/))) return setActive(m[1], m[2] === 'reactivate')
  if (path === '/api/owner/mechanics' && method === 'POST') return invite(body)
  if ((m = path.match(/^\/api\/owner\/estimates\/([^/]+)\/(send|drop)$/))) return answerEstimate(m[1], m[2] === 'send', body)
  if ((m = path.match(/^\/api\/owner\/callbacks\/([^/]+)\/done$/))) {
    store.change((st) => { const cb = st.callbacks.find((c) => c.id === m[1]); if (cb) cb.status = 'done' })
    return { callback_id: m[1], status: 'done' }
  }
  if (path === '/api/owner/diagnostics/storage') {
    const steps = [['bucket', 'Bucket name', 'in memory (demo)'], ['write', 'Save a test file'], ['read', 'Read it back'],
      ['sign', 'Make a signed link'], ['delete', 'Delete the test file']].map(([step, label, detail]) => ({ step, label, ok: true, detail: detail || 'OK' }))
    return { bucket: 'demo', ok: true, steps }
  }
  if (path === '/api/owner/settings' && method === 'GET') return { ...store.settings(s), languages: store.LANGUAGES }
  if (path === '/api/owner/settings' && method === 'PUT') return saveSettings(body.changes || {})
  if ((m = path.match(/^\/api\/jobs\/([^/]+)\/photos$/))) {
    const url = rawBody instanceof Blob ? URL.createObjectURL(rawBody) : WORN_PLATE
    store.change((st) => { st.photos[m[1]] = url.startsWith('blob:') ? WORN_PLATE : url })
    return { job_id: m[1], path: `photos/${GARAGE.id}/${m[1]}/demo.jpg`, url }
  }
  throw new DemoError(404, `Demo backend has no ${method} ${path}`)
}

function compactJob(j) {
  return {
    id: j.id, plate: j.plate, vehicle: j.vehicle, owner: j.owner, stage: j.stage, status: j.status,
    stage_started_at: j.stage_started_at, mechanic_name: j.mechanic_name, bill: j.bill, pending_quote: j.pending_quote || null,
    closed_at: j.closed_at || null, complaint: j.complaint, money: store.money(j),
  }
}

function customerView(s, jobId) {
  const j = s.jobs[jobId]
  if (!j) throw new DemoError(404, 'Job not found')
  const stages = s.stages[jobId] || []
  return {
    garage: store.settings(s).name, job_id: j.id, vehicle: j.vehicle, plate: j.plate, owner: j.owner, stage: j.stage,
    stage_label: STAGE_LABEL[j.stage], status: j.status,
    timeline: stages.map((st) => ({ name: st.name, label: STAGE_LABEL[st.name], started_at: st.started_at, minutes: st.minutes ?? null })),
    quotes: Object.entries(s.quotes).filter(([, q]) => q.job_id === jobId).map(([id, q]) => ({ id, ...q, photo_url: q.photo ? s.photos[jobId] || WORN_PLATE : null })),
    parts: j.parts.map(({ name, qty, price, total }) => ({ name, qty, price, total })),
    labour: j.labour, bill: j.bill,
    messages: s.messages.filter((m) => m.job_id === jobId && m.to === j.customer_id).reverse()
      .map((m) => ({ kind: m.kind, at: m.at, text_en: m.text_en || m.text, text_hi: m.text_hi || m.text })),
  }
}

export function dashboard(s) {
  const jobs = Object.values(s.jobs)
  const open = jobs.filter((j) => j.status === 'open')
  const today = new Date(s.now).toDateString()
  const closedToday = jobs.filter((j) => j.closed_at && new Date(j.closed_at).toDateString() === today)
  return {
    garage: { id: GARAGE.id, name: store.settings(s).name, city: store.settings(s).city },
    open_jobs: open.length,
    jobs_by_stage: Object.fromEntries(['intake', 'service', 'waiting_approval', 'washing', 'ready'].map((st) => [st, open.filter((j) => j.stage === st).length])),
    pending_approvals: Object.entries(s.quotes).filter(([, q]) => q.status === 'pending').map(([id, q]) => ({ id, ...q })),
    low_stock: Object.values(s.inventory).filter((p) => p.low_stock).map((p) => ({ part_id: p.id, name: p.name, qty: p.qty })),
    revenue_today: closedToday.reduce((t, j) => t + j.bill, 0),
    cost_today: closedToday.reduce((t, j) => t + store.money(j).cost, 0),
    margin_today: closedToday.reduce((t, j) => t + store.money(j).margin, 0),
    minutes_per_job: Object.fromEntries(closedToday.map((j) => [j.id, Object.values(j.stage_minutes).reduce((a, b) => a + b, 0)])),
    reorder_asks: Object.values(s.reorder_asks).filter((a) => a.status === 'asked'),
    jobs: [...open, ...closedToday].map(compactJob),
    messages: s.messages.slice(0, 12),
  }
}

export function ownerStock(partId, action, body) {
  let out
  store.change((s) => {
    const p = s.inventory[partId]
    if (!p) throw new DemoError(404, 'No such part')
    const owner = { uid: 'o-asha', name: 'Asha', role: 'owner' }
    if (action === 'restock') {
      p.qty += body.qty
      p.low_stock = p.qty <= store.lowAt(s, p)
      p.reorder_pending = false
      if (!p.low_stock) delete s.reorder_asks[partId]
      out = { part_id: partId, qty: p.qty }
    } else if (action === 'reorder') {
      const { supplier, name, reorder_qty } = store.settings(s)
      const qty = body.qty || p.reorder_qty || reorder_qty
      out = { part_id: partId, name: p.name, qty, supplier, status: 'ordered', at: s.now, by: 'Asha' }
      p.reorder_pending = true
      if (s.reorder_asks[partId]) s.reorder_asks[partId].status = 'ordered'
      store.notify(s, `supplier:${supplier}`, 'reorder', `${name} order: ${qty} x ${p.name} (${p.fits.join(', ')}).`, { part_id: partId })
    } else {
      if (s.reorder_asks[partId]) s.reorder_asks[partId].status = 'later'
      out = { part_id: partId, status: 'later' }
    }
    store.audit(s, action === 'reorder-later' ? 'reorder_later' : action, out, owner)
  })
  return out
}

const LABELS = { quote_limit: 'auto-approve limit', name: 'garage name', city: 'city', lang: 'customer language', supplier: 'supplier', reorder_qty: 'reorder quantity', low_at: 'low-stock level' }
const shown = (f, v) => (f === 'quote_limit' ? `₹${v}` : f === 'lang' ? store.LANGUAGES[v] || v : String(v))

// Same rules as services/settings.py: whole numbers in range, known language, a garage name.
export function saveSettings(changes) {
  const range = { quote_limit: [0, 100000], reorder_qty: [1, 999], low_at: [0, 999] }
  const clean = {}
  for (const [f, v] of Object.entries(changes)) {
    if (!(f in LABELS)) throw new DemoError(409, `unknown setting: ${f}`)
    if (range[f]) {
      const n = Number(String(v).replace(/,/g, '').trim())
      if (String(v).trim() === '' || !Number.isInteger(n)) throw new DemoError(409, `${LABELS[f]} must be a whole number`)
      if (n < range[f][0] || n > range[f][1]) throw new DemoError(409, `${LABELS[f]} must be between ${range[f][0].toLocaleString('en-IN')} and ${range[f][1].toLocaleString('en-IN')}`)
      clean[f] = n
    } else if (f === 'lang') {
      if (!store.LANGUAGES[v]) throw new DemoError(409, 'customer language is not supported')
      clean[f] = v
    } else {
      clean[f] = String(v || '').trim().slice(0, 60)
      if (f === 'name' && !clean[f]) throw new DemoError(409, "garage name can't be empty")
    }
  }
  let out
  store.change((s) => {
    const before = store.settings(s)
    const changed = Object.entries(clean).filter(([f, v]) => before[f] !== v)
    s.settings = { ...before, ...clean }
    if (clean.low_at != null) for (const p of Object.values(s.inventory)) p.low_stock = p.qty <= store.lowAt(s, p)
    const lines = changed.map(([f, v]) => `the ${LABELS[f]} from ${shown(f, before[f])} to ${shown(f, v)}`)
    out = { changes: changed.map(([f, v]) => ({ field: f, from: before[f], to: v })), summary: lines.length ? `changed ${lines.join('; ')}` : 'saved settings (no changes)' }
    store.audit(s, 'update_settings', out, { uid: 'o-asha', name: 'Asha', role: 'owner' })
  })
  return { ...out, settings: { ...store.settings(store.get()), languages: store.LANGUAGES } }
}

// ---------------------------------------------------------------- owner records (C17)

const OWNER = { uid: 'o-asha', name: 'Asha', role: 'owner' }
const notFound = () => { throw new DemoError(404, 'Not found') }

function resendLink(jobId) {
  let out
  store.change((s) => {
    const j = s.jobs[jobId]
    if (!j) throw new DemoError(404, 'Job not found')
    const text = `Hi ${j.owner}, track your ${j.vehicle}: gc.app/j/demo-${j.id}`
    store.notify(s, j.customer_id, 'status_link', text, { job_id: j.id, text_en: text, text_hi: `नमस्ते ${j.owner}, अपनी ${j.vehicle} यहाँ देखें: gc.app/j/demo-${j.id}` })
    out = { job_id: jobId, sent_to: j.owner }
    store.audit(s, 'send_status_link', out, OWNER)
  })
  return out
}

function setActive(uid, active) {
  let out
  store.change((s) => {
    const person = (s.mechanics || []).find((x) => x.uid === uid)
    if (!person) throw new DemoError(404, 'No such mechanic')
    person.active = active
    out = { uid, name: person.name, active }
    store.audit(s, active ? 'reactivate_mechanic' : 'deactivate_mechanic', out, OWNER)
  })
  return out
}

function invite(body) {
  const name = String(body.name || '').trim()
  if (!name) throw new DemoError(409, 'name is required')
  if (body.pin && !/^\d{4,6}$/.test(body.pin)) throw new DemoError(409, 'PIN must be 4 to 6 digits')
  let out
  store.change((s) => {
    const uid = `m-${name.toLowerCase().replace(/\W/g, '')}`
    const existing = s.mechanics.find((x) => x.uid === uid)
    const person = { uid, name, phone: body.phone || '', active: true, pin: body.pin || existing?.pin || '1234' }
    s.mechanics = [...s.mechanics.filter((x) => x.uid !== uid), person]
    out = { uid, name, phone: person.phone, has_pin: !!body.pin }
    store.audit(s, 'invite_mechanic', out, OWNER)
  })
  return out
}

// ---------------------------------------------------------------- front desk (C15)

function startCall(verified, phone = '+91 98000 00101') {
  let call
  store.change((s) => {
    call = { id: `C-${s.calls.length + 1}`, phone: phone.replace(/\D/g, '').slice(-10), verified, via: verified ? 'status page' : 'web',
      started_at: s.now, status: 'live', heard: [], actions: [] }
    s.calls.unshift(call)
  })
  return { call_id: call.id, token: `demo-call:${call.id}`, verified }
}

function callsOverview(s) {
  return {
    calls: s.calls.slice(0, 30).map((c) => ({ ...c, summary: c.heard.slice(0, 2).join(' · ') || '(no words heard)' })),
    callbacks: s.callbacks.filter((c) => c.status === 'open'),
    estimates: s.estimates.filter((e) => e.status === 'asked'),
    bookings: s.bookings.filter((b) => b.status === 'booked'),
  }
}

function answerEstimate(id, send, body) {
  let out
  store.change((s) => {
    const e = s.estimates.find((x) => x.id === id)
    if (!e) throw new DemoError(404, 'No such estimate')
    if (e.status !== 'asked') throw new DemoError(409, `${id} is already ${e.status}`)
    const owner = { uid: 'o-asha', name: 'Asha', role: 'owner' }
    if (!send) {
      e.status = 'dropped'
      out = { estimate_id: id, status: 'dropped' }
    } else {
      e.status = 'sent'
      e.total = body.total ?? e.total
      const text = `Hi${e.name ? ` ${e.name}` : ''}, ${store.settings(s).name} here. Estimate for ${e.work} on your ${e.vehicle}: about ₹${e.total} (parts and labour). The final price is confirmed after we inspect the vehicle.`
      store.notify(s, `c-${e.phone}`, 'estimate', text, { estimate_id: id, text_en: text, text_hi: text })
      out = { estimate_id: id, status: 'sent', total: e.total }
    }
    store.audit(s, 'answer_estimate', out, owner)
  })
  return out
}

// A stand-in for the mechanic's photo of a worn clutch plate.
export const WORN_PLATE = `data:image/svg+xml;utf8,${encodeURIComponent(`
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 260">
  <defs>
    <radialGradient id="g" cx="50%" cy="45%" r="60%"><stop offset="0" stop-color="#5b4a3b"/><stop offset="1" stop-color="#1e1813"/></radialGradient>
    <radialGradient id="p" cx="45%" cy="40%" r="55%"><stop offset="0" stop-color="#a08060"/><stop offset=".7" stop-color="#6d543d"/><stop offset="1" stop-color="#3a2c20"/></radialGradient>
  </defs>
  <rect width="400" height="260" fill="url(#g)"/>
  <circle cx="200" cy="130" r="104" fill="url(#p)"/>
  <circle cx="200" cy="130" r="44" fill="#2a2119"/>
  <g stroke="#c9b08f" stroke-opacity=".35" stroke-width="3">${Array.from({ length: 24 }, (_, i) => {
    const a = (i / 24) * Math.PI * 2
    return `<line x1="${200 + 54 * Math.cos(a)}" y1="${130 + 54 * Math.sin(a)}" x2="${200 + 98 * Math.cos(a)}" y2="${130 + 98 * Math.sin(a)}"/>`
  }).join('')}</g>
  <ellipse cx="170" cy="105" rx="46" ry="22" fill="#e9dcc6" fill-opacity=".28" transform="rotate(-25 170 105)"/>
</svg>`)}`
