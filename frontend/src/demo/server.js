// Demo backend: answers the same REST calls as the FastAPI service, from the in-browser store.
import { STAGE_LABEL } from '../format.js'
import * as store from './store.js'
import { GARAGE } from './store.js'

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
  if (path.startsWith('/api/j/')) throw new DemoError(403, 'This link is invalid or has expired.')

  if (path === '/api/auth/pin') {
    const ok = body.garage_id === GARAGE.id && ['raju', 'salim'].includes(body.name.trim().toLowerCase()) && body.pin === '1234'
    if (!ok) throw new DemoError(401, 'Wrong name or PIN')
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
    closed_at: j.closed_at || null, complaint: j.complaint,
  }
}

function customerView(s, jobId) {
  const j = s.jobs[jobId]
  if (!j) throw new DemoError(404, 'Job not found')
  const stages = s.stages[jobId] || []
  return {
    garage: GARAGE.name, job_id: j.id, vehicle: j.vehicle, plate: j.plate, owner: j.owner, stage: j.stage,
    stage_label: STAGE_LABEL[j.stage], status: j.status,
    timeline: stages.map((st) => ({ name: st.name, label: STAGE_LABEL[st.name], started_at: st.started_at, minutes: st.minutes ?? null })),
    quotes: Object.entries(s.quotes).filter(([, q]) => q.job_id === jobId).map(([id, q]) => ({ id, ...q, photo_url: q.photo ? s.photos[jobId] || WORN_PLATE : null })),
    parts: j.parts.map(({ name, qty, price, total }) => ({ name, qty, price, total })),
    labour: j.labour, bill: j.bill,
  }
}

export function dashboard(s) {
  const jobs = Object.values(s.jobs)
  const open = jobs.filter((j) => j.status === 'open')
  const today = new Date(s.now).toDateString()
  const closedToday = jobs.filter((j) => j.closed_at && new Date(j.closed_at).toDateString() === today)
  return {
    garage: { id: GARAGE.id, name: GARAGE.name, city: GARAGE.city },
    open_jobs: open.length,
    jobs_by_stage: Object.fromEntries(['intake', 'washing', 'service', 'waiting_approval', 'ready'].map((st) => [st, open.filter((j) => j.stage === st).length])),
    pending_approvals: Object.entries(s.quotes).filter(([, q]) => q.status === 'pending').map(([id, q]) => ({ id, ...q })),
    low_stock: Object.values(s.inventory).filter((p) => p.low_stock).map((p) => ({ part_id: p.id, name: p.name, qty: p.qty })),
    revenue_today: closedToday.reduce((t, j) => t + j.bill, 0),
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
      p.low_stock = p.qty <= p.low_at
      p.reorder_pending = false
      if (!p.low_stock) delete s.reorder_asks[partId]
      out = { part_id: partId, qty: p.qty }
    } else if (action === 'reorder') {
      const qty = body.qty || p.reorder_qty
      out = { part_id: partId, name: p.name, qty, supplier: GARAGE.supplier, status: 'ordered', at: s.now, by: 'Asha' }
      p.reorder_pending = true
      if (s.reorder_asks[partId]) s.reorder_asks[partId].status = 'ordered'
      store.notify(s, `supplier:${GARAGE.supplier}`, 'reorder', `${GARAGE.name} order: ${qty} x ${p.name} (${p.fits.join(', ')}).`, { part_id: partId })
    } else {
      if (s.reorder_asks[partId]) s.reorder_asks[partId].status = 'later'
      out = { part_id: partId, status: 'later' }
    }
    store.audit(s, action === 'reorder-later' ? 'reorder_later' : action, out, owner)
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
