// Demo backend state: a small copy of the seeded Shree Auto garage, kept in localStorage so every
// tab (mechanic, owner, customer) sees the same data and updates live. Mirrors the backend's
// service layer just enough for the demo job in diagrams/job-workflow.png.

const KEY = 'gc.demo.v3' // bump when the seed's shape changes, so old saved demos start fresh
export const GARAGE = { id: 'shree-auto', name: 'Shree Auto', city: 'Pune', quote_limit: 500, supplier: 'Sai Spares' }
// What the owner can change in Settings (C09); the demo reads these, not GARAGE, wherever the backend reads config.
const SETTINGS = { quote_limit: 500, name: 'Shree Auto', city: 'Pune', lang: 'mr', supplier: 'Sai Spares', reorder_qty: 5, low_at: 1 }
export const LANGUAGES = { en: 'English', hi: 'Hindi', mr: 'Marathi', gu: 'Gujarati', kn: 'Kannada', ta: 'Tamil', te: 'Telugu', bn: 'Bengali', ml: 'Malayalam', pa: 'Punjabi' }

export function settings(s) {
  return s.settings || SETTINGS
}

export function lowAt(s, p) {
  return p.low_at ?? settings(s).low_at
}

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

// Consumables (C13), like the backend seed: [id, name, qty, price, cost, billable, low_at]
const CONSUMABLES = [
  ['gasket-clutch-cover', 'Clutch cover gasket', 12, 90, 45, false, 3],
  ['bolt-m6', 'M6 bolt', 150, 5, 2, false, 20],
  ['washer-m6', 'M6 washer', 200, 2, 1, false, 30],
  ['grease-10g', 'Grease (10 g)', 60, 15, 8, false, 10],
  ['split-pin', 'Split pin', 80, 3, 1, false, 10],
  ['brake-cleaner-shot', 'Brake cleaner (one job)', 30, 30, 20, true, 5],
  ['chain-lube-shot', 'Chain lube (one job)', 40, 40, 18, true, 6],
  ['drain-washer', 'Oil drain plug washer', 100, 15, 4, true, 15],
]
const WITH = {
  'clutch-splendor': [['gasket-clutch-cover', 1], ['bolt-m6', 4], ['washer-m6', 4], ['grease-10g', 1]],
  'brake-shoe-splendor': [['split-pin', 2], ['grease-10g', 1], ['brake-cleaner-shot', 1]],
  'brake-pad-activa': [['split-pin', 2], ['brake-cleaner-shot', 1]],
  'chain-kit-splendor': [['split-pin', 1], ['chain-lube-shot', 1]],
  'engine-oil-1l': [['drain-washer', 1]],
}
const partCost = (price) => Math.round((price * 0.7) / 5) * 5

// Demo day times are in IST, like the diagram.
export function at(hhmm) {
  const d = new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
  return new Date(`${d}T${hhmm}:00+05:30`).toISOString()
}

// A bill line for the seeded jobs (cost: what the garage paid, about 70%).
const line = (name, price, qty = 1) => ({ part_id: name.toLowerCase().replace(/\W+/g, '-'), name, qty, price, total: price * qty, cost: partCost(price) * qty })

function job(id, plate, vehicle, owner, stage, extra = {}) {
  return {
    id, plate, vehicle, owner, phone: '', customer_id: `c-${owner.toLowerCase()}`, lang: 'mr', complaint: 'general service',
    stage, status: 'open', mechanic_uid: 'm-salim', mechanic_name: 'Salim', created_at: at('09:10'),
    stage_started_at: at('09:40'), quote_limit: 500, parts: [], labour: 0, bill: 0, stage_minutes: {}, ...extra,
  }
}

// Owner records (C17): // A few weeks of closed jobs before today, so the records pages aren't empty. Not used by the demo job script.
const PEOPLE = [
  ['Sunita', 'MH12DE4521', 'Activa 6G'], ['Vikas', 'MH14GH7710', 'Pulsar 150'], ['Meena', 'MH12JK3302', 'Activa 6G'],
  ['Arjun', 'MH12LM8890', 'Pulsar 150'], ['Kiran', 'MH12QR1188', 'Splendor Plus'], ['Prakash', 'MH12XY4410', 'Honda Shine'],
  ['Farhan', 'MH12PQ6612', 'TVS Jupiter'], ['Neha', 'MH12CD7781', 'Activa 6G'], ['Rohit', 'MH12EF2290', 'Splendor Plus'],
  ['Anjali', 'MH14KL5503', 'Splendor Plus'], ['Imran', 'MH12MN6620', 'Pulsar 150'], ['Pooja', 'MH12ST9014', 'TVS Jupiter'],
]
const WORK = [
  ['general service', [['Engine oil 1L 10W30', 380], ['Air filter', 180], ['Spark plug', 120]], 300],
  ['brakes weak', [['Brake shoe set', 260]], 150],
  ['chain noise', [['Chain sprocket kit', 1150]], 250],
  ['clutch slipping', [['Clutch plate set', 650]], 300],
  ['battery dead', [['Battery 12V 5Ah', 1450]], 100],
  ['headlight not working', [['Headlight bulb 35W', 110]], 50],
  ['oil change', [['Engine oil 1L 10W30', 380]], 100],
]
const MECHS = [['m-raju', 'Raju'], ['m-salim', 'Salim']]
const addDays = (ymd, n) => {
  const d = new Date(`${ymd}T12:00:00+05:30`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })
}

function historyJobs(todayYmd) {
  let seed = 7
  const rand = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648)
  const out = {}
  let n = 930
  for (let back = 28; back >= 1; back--) {
    const date = addDays(todayYmd, -back)
    const weekday = new Date(`${date}T12:00:00+05:30`).getUTCDay()
    const count = weekday === 0 ? 0 : 1 + Math.floor(rand() * 3) // closed on Sundays
    for (let k = 0; k < count && n < 1035; k++) {
      const [owner, plate, vehicle] = PEOPLE[Math.floor(rand() * PEOPLE.length)]
      const [complaint, parts, labour] = WORK[Math.floor(rand() * WORK.length)]
      const [uid, name] = MECHS[Math.floor(rand() * MECHS.length)]
      const start = 9 + Math.floor(rand() * 6)
      const intake = 5 + Math.floor(rand() * 15)
      const service = 30 + Math.floor(rand() * 120)
      const wash = 10 + Math.floor(rand() * 15)
      const created = new Date(`${date}T${String(start).padStart(2, '0')}:${String(Math.floor(rand() * 50)).padStart(2, '0')}:00+05:30`)
      const closed = new Date(created.getTime() + (intake + service + wash) * 60000)
      const lines = parts.map(([pname, price]) => line(pname, price))
      const id = `J-${String(n++).padStart(4, '0')}`
      out[id] = {
        id, plate, vehicle, owner, phone: `+91 98000 ${String(10000 + PEOPLE.findIndex((p) => p[0] === owner) * 1111).slice(0, 5)}`,
        customer_id: `c-${owner.toLowerCase()}`, lang: 'en', complaint, stage: 'done', status: 'done', mechanic_uid: uid, mechanic_name: name,
        created_at: created.toISOString(), stage_started_at: closed.toISOString(), closed_at: closed.toISOString(), quote_limit: 500,
        parts: lines, labour, bill: lines.reduce((t, l) => t + l.total, 0) + labour, stage_minutes: { intake, service, washing: wash },
      }
    }
  }
  return out
}

export function seed() {
  return {
    now: at('10:00'),
    next_job_no: 1042,
    next_quote_no: 77,
    jobs: {
      ...historyJobs(new Date(at('10:00')).toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })),
      'J-1039': job('J-1039', 'MH12DE4521', 'Activa 6G', 'Sunita', 'done', {
        status: 'done', closed_at: at('09:55'), bill: 4850, labour: 900, stage_minutes: { intake: 15, service: 70 },
        parts: [line('Drive belt', 750), line('Variator roller set', 420), line('Brake shoe set', 280), line('Battery 12V 5Ah', 1450),
          line('Air filter', 220), line('Engine oil 1L 10W30', 380), line('Spark plug', 120), line('Clutch shoe set', 330)],
      }),
      'J-1038': job('J-1038', 'MH14GH7710', 'Pulsar 150', 'Vikas', 'done', {
        status: 'done', closed_at: at('09:30'), bill: 6600, labour: 1200, stage_minutes: { intake: 10, service: 95 },
        parts: [line('Chain sprocket kit', 1650), line('Clutch plate set', 820), line('Front disc brake pad', 450), line('Oil filter', 150),
          line('Engine oil 1L 10W30', 380, 2), line('Battery 12V 5Ah', 1450), line('Spark plug', 120)],
      }),
      'J-1040': job('J-1040', 'MH12JK3302', 'Activa 6G', 'Meena', 'washing'),
      'J-1041': job('J-1041', 'MH12LM8890', 'Pulsar 150', 'Arjun', 'service', { mechanic_uid: 'm-raju', mechanic_name: 'Raju' }),
      'J-1037': job('J-1037', 'MH12QR1188', 'Splendor Plus', 'Kiran', 'service'),
      // Not touched by the demo script: they fill the owner's 3D floor (one at the door, one ready for pickup)
      'J-1035': job('J-1035', 'MH12XY4410', 'Honda Shine', 'Prakash', 'intake', { mechanic_uid: '', mechanic_name: '', stage_started_at: at('09:50') }),
      'J-1036': job('J-1036', 'MH12PQ6612', 'TVS Jupiter', 'Farhan', 'ready', {
        bill: 1850, labour: 450, stage_started_at: at('09:45'),
        parts: [line('Variator roller set', 420), line('Brake shoe set', 280), line('Engine oil 1L 10W30', 380), line('Air filter', 200), line('Spark plug', 120)],
      }),
    },
    settings: { ...SETTINGS },
    mechanics: [{ uid: 'm-raju', name: 'Raju', phone: '+91 98000 00011', active: true }, { uid: 'm-salim', name: 'Salim', phone: '+91 98000 00012', active: true }],
    calls: [], callbacks: [], estimates: [], bookings: [], // front desk (C15)
    stages: {},
    quotes: {},
    inventory: Object.fromEntries([
      ...PARTS.map(([id, name, fits, qty, price, labour]) => [id, {
        id, name, fits, qty, price, cost: partCost(price), labour, low_stock: qty <= SETTINGS.low_at,
        ...(WITH[id] ? { with: WITH[id].map(([part_id, n]) => ({ part_id, qty: n })) } : {}),
      }]),
      ...CONSUMABLES.map(([id, name, qty, price, cost, billable, low_at]) => [id, {
        id, name, fits: ['universal'], qty, price, cost, labour: 0, kind: 'consumable', billable, low_at, low_stock: qty <= low_at, reorder_qty: low_at * 4,
      }]),
    ]),
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
    created_at: s.now, quote_limit: settings(s).quote_limit, parts: [], labour: 0, bill: 0, stage_minutes: {},
  }
  s.stages[id] = [{ name: 'intake', started_at: s.now }]
  audit(s, 'create_job', { job_id: id, plate, owner, stage: 'intake' })
  const name = settings(s).name
  notify(s, 'c-919800000101', 'status_link', `नमस्कार ${owner}, तुमची ${vehicle} ${name} मध्ये आली आहे. इथे पाहा: gc.app/j/demo-${id}`, {
    job_id: id,
    text_en: `Hi ${owner}, your ${vehicle} is checked in at ${name}. Track it: gc.app/j/demo-${id}`,
    text_hi: `नमस्ते ${owner}, आपकी ${vehicle} ${name} में जमा हो गई है। यहाँ देखें: gc.app/j/demo-${id}`,
  })
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

// A part fitted on a job with its consumables (services/inventory.log_part_used): billable ones become bill lines,
// the rest the garage's own cost on job.consumables. Returns the line the agent says.
export function logPart(s, j, p, qty = 1) {
  p.qty -= qty
  p.low_stock = p.qty <= lowAt(s, p)
  j.parts.push({ part_id: p.id, name: p.name, qty, price: p.price, total: p.price * qty, cost: (p.cost || 0) * qty })
  let fittings = 0
  for (const w of p.with || []) {
    const c = s.inventory[w.part_id]
    if (!c) continue
    const need = w.qty * qty
    c.qty = Math.max(0, c.qty - need)
    c.low_stock = c.qty <= lowAt(s, c)
    const entry = { part_id: c.id, name: c.name, qty: need, cost: c.cost * need, with: p.id }
    if (c.billable) j.parts.push({ ...entry, price: c.price, total: c.price * need, consumable: true })
    else (j.consumables ||= []).push(entry)
    fittings += 1
  }
  j.bill = billOf(j)
  return fittings ? ' and the usual fittings' : ''
}

// Bill split, cost of what was used and margin (jobs.money in the backend).
export function money(j) {
  const parts = j.parts.filter((l) => !l.consumable).reduce((t, l) => t + l.total, 0)
  const consumables = j.parts.filter((l) => l.consumable).reduce((t, l) => t + l.total, 0)
  const cost = j.parts.reduce((t, l) => t + (l.cost || 0), 0) + (j.consumables || []).reduce((t, c) => t + c.cost, 0)
  const bill = parts + consumables + j.labour
  return { parts, consumables, labour: j.labour, bill, cost, margin: bill - cost }
}
