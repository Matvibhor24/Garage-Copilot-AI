// Demo backend state: a small copy of the seeded Shree Auto garage, kept in localStorage so every
// tab (mechanic, owner, customer) sees the same data and updates live. Mirrors the backend's
// service layer just enough for the demo job in diagrams/job-workflow.png.

const KEY = 'gc.demo.v1'
export const GARAGE = { id: 'shree-auto', name: 'Shree Auto', city: 'Pune', quote_limit: 500, supplier: 'Sai Spares' }

const PARTS = [
  ['clutch-splendor', 'Clutch plate set', ['Splendor', 'Splendor Plus'], 2, 650, 300],
  ['clutch-pulsar', 'Clutch plate set', ['Pulsar 150'], 3, 820, 350],
  ['clutch-cable-splendor', 'Clutch cable', ['Splendor', 'Splendor Plus'], 6, 140, 80],
  ['brake-shoe-splendor', 'Brake shoe set', ['Splendor', 'Splendor Plus'], 6, 260, 150],
  ['brake-pad-pulsar', 'Front disc brake pad', ['Pulsar 150', 'Apache'], 4, 450, 150],
  ['brake-pad-activa', 'Brake shoe set', ['Activa', 'Jupiter'], 5, 280, 150],
  ['chain-kit-splendor', 'Chain sprocket kit', ['Splendor', 'Splendor Plus'], 3, 1150, 250],
  ['engine-oil-1l', 'Engine oil 1L 10W30', ['universal'], 24, 380, 0],
  ['air-filter-splendor', 'Air filter', ['Splendor', 'Splendor Plus'], 7, 180, 50],
  ['spark-plug', 'Spark plug', ['universal'], 20, 120, 50],
  ['battery-12v-5ah', 'Battery 12V 5Ah', ['universal'], 3, 1450, 100],
  ['tyre-rear-splendor', 'Rear tyre 2.75-18', ['Splendor', 'Splendor Plus'], 2, 1650, 150],
  ['drive-belt-activa', 'Drive belt', ['Activa'], 2, 750, 300],
  ['headlight-bulb', 'Headlight bulb 35W', ['universal'], 12, 110, 50],
]

// Demo day times are in IST, like the diagram.
export function at(hhmm) {
  const d = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  return new Date(`${d}T${hhmm}:00+05:30`).toISOString()
}

function job(id, plate, vehicle, owner, stage, extra = {}) {
  return {
    id, plate, vehicle, owner, phone: '', customer_id: `c-${owner.toLowerCase()}`, lang: 'mr', complaint: 'general service',
    stage, status: 'open', mechanic_uid: 'm-salim', mechanic_name: 'Salim', created_at: at('09:10'),
    stage_started_at: at('09:40'), quote_limit: 500, parts: [], labour: 0, bill: 0, stage_minutes: {}, ...extra,
  }
}

export function seed() {
  return {
    now: at('10:00'),
    next_job_no: 1042,
    next_quote_no: 77,
    jobs: {
      'J-1039': job('J-1039', 'MH12DE4521', 'Activa 6G', 'Sunita', 'done', { status: 'done', closed_at: at('09:55'), bill: 4850, labour: 900, stage_minutes: { intake: 15, service: 70 } }),
      'J-1038': job('J-1038', 'MH14GH7710', 'Pulsar 150', 'Vikas', 'done', { status: 'done', closed_at: at('09:30'), bill: 6600, labour: 1200, stage_minutes: { intake: 10, service: 95 } }),
      'J-1040': job('J-1040', 'MH12JK3302', 'Activa 6G', 'Meena', 'washing'),
      'J-1041': job('J-1041', 'MH12LM8890', 'Pulsar 150', 'Arjun', 'service', { mechanic_uid: 'm-raju', mechanic_name: 'Raju' }),
      'J-1037': job('J-1037', 'MH12QR1188', 'Splendor Plus', 'Kiran', 'service'),
      // Not touched by the demo script: they fill the owner's 3D floor (one at the door, one ready for pickup)
      'J-1035': job('J-1035', 'MH12XY4410', 'Honda Shine', 'Prakash', 'intake', { mechanic_uid: '', mechanic_name: '', stage_started_at: at('09:50') }),
      'J-1036': job('J-1036', 'MH12PQ6612', 'TVS Jupiter', 'Farhan', 'ready', { bill: 1850, labour: 450, stage_started_at: at('09:45') }),
    },
    stages: {},
    quotes: {},
    inventory: Object.fromEntries(PARTS.map(([id, name, fits, qty, price, labour]) => [id, { id, name, fits, qty, price, labour, low_at: 1, low_stock: qty <= 1, reorder_qty: 5 }])),
    messages: [],
    audit: [],
    reorder_asks: {},
    photos: {},
    history: { MH12AB1234: [{ job_id: 'J-0957', date: '2026-02-12', months_ago: 8, complaint: 'clutch hard, service', parts: ['Clutch cable'], bill: 220 }] },
  }
}

let state = read() || seed()
const listeners = new Set()

function read() {
  try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null }
}

export function get() {
  return state
}

// Apply a change, persist it, and tell this tab and every other tab.
export function change(fn) {
  fn(state)
  try { localStorage.setItem(KEY, JSON.stringify(state)) } catch { /* quota or private mode */ }
  listeners.forEach((l) => l())
}

export function reset() {
  state = seed()
  change(() => {})
}

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key !== KEY) return
    state = read() || seed()
    listeners.forEach((l) => l())
  })
}

// ---------------------------------------------------------------- actions (like the service layer)

const RAJU = { uid: 'm-raju', name: 'Raju', role: 'mechanic' }

export function audit(s, action, details, who = RAJU) {
  s.audit.unshift({ at: s.now, action, by_uid: who.uid, by_name: who.name, by_role: who.role, details })
}

export function notify(s, to, kind, text, extra = {}) {
  const channel = to.startsWith('c-') || to.startsWith('supplier:') ? 'whatsapp' : to === 'owner' ? 'owner_app' : 'headset'
  s.messages.unshift({ id: Math.random().toString(36).slice(2, 10), to, kind, text, channel, at: s.now, status: 'sent (simulated)', ...extra })
}

export function billOf(j) {
  return j.parts.reduce((t, p) => t + p.total, 0) + j.labour
}

export function moveStage(s, j, stage) {
  const list = (s.stages[j.id] ||= [])
  const last = list[list.length - 1]
  const mins = Math.round((new Date(s.now) - new Date(j.stage_started_at)) / 60000)
  if (last) Object.assign(last, { ended_at: s.now, minutes: mins })
  j.stage_minutes[j.stage] = mins
  list.push({ name: stage, started_at: s.now })
  j.stage = stage
  j.stage_started_at = s.now
  return mins
}

export function createJob(s, plate, vehicle, owner, complaint) {
  const id = `J-${s.next_job_no++}`
  s.jobs[id] = {
    id, plate, vehicle, owner, phone: '+91 98000 00101', customer_id: 'c-919800000101', lang: 'mr', complaint,
    stage: 'intake', stage_started_at: s.now, status: 'open', mechanic_uid: 'm-raju', mechanic_name: 'Raju',
    created_at: s.now, quote_limit: GARAGE.quote_limit, parts: [], labour: 0, bill: 0, stage_minutes: {},
  }
  s.stages[id] = [{ name: 'intake', started_at: s.now }]
  audit(s, 'create_job', { job_id: id, plate, owner, stage: 'intake' })
  notify(s, 'c-919800000101', 'status_link', `नमस्कार ${owner}, तुमची ${vehicle} ${GARAGE.name} मध्ये आली आहे. इथे पाहा: gc.app/j/demo-${id}`, { job_id: id })
  return s.jobs[id]
}

export function decideQuote(s, quoteId, decision) {
  const q = s.quotes[quoteId]
  if (!q) throw new Error('No such quote')
  if (q.status !== 'pending') return { quote_id: quoteId, status: q.status, total: q.total }
  const j = s.jobs[q.job_id]
  Object.assign(q, { status: decision, by: 'customer', at: s.now })
  j.pending_quote = null
  if (decision === 'approved') {
    j.labour += q.labour
    j.bill = billOf(j)
  }
  audit(s, `quote_${decision}`, { quote_id: quoteId, status: decision, total: q.total }, { uid: 'customer', name: j.owner, role: 'customer' })
  notify(s, j.mechanic_uid, `quote_${decision}`, decision === 'approved' ? `${j.owner} approved. Go ahead.` : `${j.owner} rejected the quote. Do not fit the parts.`, { job_id: j.id, quote_id: quoteId })
  return { quote_id: quoteId, status: decision, total: q.total }
}
