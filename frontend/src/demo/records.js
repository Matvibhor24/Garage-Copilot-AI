// Owner records in demo mode (C17): the same answers as backend/app/services/reports.py, from the demo store.
// Also makes a few weeks of plausible closed jobs for the seed (fixed pseudo-random, so every run is the same).
import { money } from './store.js'

const IST = 'Asia/Kolkata'
export const day = (iso) => (iso ? new Date(iso).toLocaleDateString('en-CA', { timeZone: IST }) : '')
const addDays = (ymd, n) => {
  const d = new Date(`${ymd}T12:00:00+05:30`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toLocaleDateString('en-CA', { timeZone: IST })
}

export function periodRange(period, today) {
  const d = new Date(`${today}T12:00:00+05:30`)
  if (period === 'week') return [addDays(today, -((d.getUTCDay() + 6) % 7)), today]
  if (period === 'month') return [`${today.slice(0, 8)}01`, today]
  return [today, today]
}

const minutesTaken = (j, now) => Object.values(j.stage_minutes || {}).reduce((a, b) => a + b, 0)
  + (j.status === 'open' && j.stage_started_at ? Math.max(0, Math.round((new Date(now) - new Date(j.stage_started_at)) / 60000)) : 0)

function row(j, now) {
  const m = money(j)
  return {
    job_id: j.id, date: day(j.created_at), created_at: j.created_at, closed_at: j.closed_at || '', vehicle: j.vehicle, plate: j.plate,
    customer: j.owner, customer_id: j.customer_id, mechanic: j.mechanic_name || '', status: j.status === 'done' ? 'closed' : 'open', stage: j.stage,
    parts: m.parts, consumables: m.consumables, labour: m.labour, bill: m.bill, cost: m.cost, margin: m.margin, minutes: minutesTaken(j, now),
  }
}

export function jobRows(s, { from = '', to = '', status = '', mechanic = '', q = '' } = {}) {
  const plate = q.toUpperCase().replace(/[^A-Z0-9]/g, '')
  return Object.values(s.jobs)
    .filter((j) => {
      const d = day(j.created_at)
      if (from && d < from) return false
      if (to && d > to) return false
      const closed = j.status === 'done'
      if ((status === 'open' && closed) || (status === 'closed' && !closed)) return false
      if (mechanic && ![j.mechanic_name, j.mechanic_uid].map((x) => (x || '').toLowerCase()).includes(mechanic.toLowerCase())) return false
      if (q && !`${j.id} ${j.owner} ${j.vehicle}`.toLowerCase().includes(q.trim().toLowerCase()) && !(plate && j.plate.includes(plate))) return false
      return true
    })
    .sort((a, b) => (b.created_at + b.id).localeCompare(a.created_at + a.id))
    .map((j) => row(j, s.now))
}

export function totals(rows) {
  const closed = rows.filter((r) => r.status === 'closed')
  const revenue = closed.reduce((t, r) => t + r.bill, 0)
  return {
    jobs: rows.length, closed: closed.length, revenue, cost: closed.reduce((t, r) => t + r.cost, 0), margin: closed.reduce((t, r) => t + r.margin, 0),
    average_bill: closed.length ? Math.round(revenue / closed.length) : 0,
    average_minutes: closed.length ? Math.round(closed.reduce((t, r) => t + r.minutes, 0) / closed.length) : 0,
  }
}

export function jobsPage(s, filter, cursor = '') {
  const rows = jobRows(s, filter)
  const start = Number(cursor) || 0
  return { jobs: rows.slice(start, start + 50), totals: totals(rows), next_cursor: start + 50 < rows.length ? String(start + 50) : '' }
}

const CSV_FIELDS = ['date', 'job_id', 'vehicle', 'plate', 'customer', 'mechanic', 'status', 'parts', 'consumables', 'labour', 'bill', 'cost', 'margin', 'minutes', 'closed_at']
export function jobsCsv(s, filter) {
  const esc = (v) => (/[",\n]/.test(String(v)) ? `"${String(v).replaceAll('"', '""')}"` : String(v))
  return [CSV_FIELDS.join(','), ...jobRows(s, filter).map((r) => CSV_FIELDS.map((f) => esc(r[f] ?? '')).join(','))].join('\r\n') + '\r\n'
}

export function jobDetail(s, id, labels) {
  const j = s.jobs[id]
  if (!j) return null
  const quotes = Object.entries(s.quotes).filter(([, q]) => q.job_id === id).map(([qid, q]) => ({ id: qid, ...q }))
  return {
    ...j, money: money(j), minutes: minutesTaken(j, s.now),
    timeline: (s.stages[id] || []).map((st) => ({ name: st.name, label: labels[st.name] || st.name, started_at: st.started_at, minutes: st.minutes ?? null })),
    quotes, messages: s.messages.filter((m) => m.job_id === id).slice().reverse(),
    photos: s.photos[id] ? [{ path: `photos/demo/${id}`, url: s.photos[id] }] : [],
  }
}

export function customers(s, q = '') {
  const byId = {}
  for (const j of Object.values(s.jobs)) {
    const c = (byId[j.customer_id] ||= { id: j.customer_id, name: j.owner, phone: j.phone || '', lang: j.lang || 'en', jobs: [] })
    c.jobs.push(j)
  }
  let out = Object.values(byId).map((c) => ({
    id: c.id, name: c.name, phone: c.phone, lang: c.lang,
    vehicles: [...new Set(c.jobs.map((j) => `${j.vehicle} · ${j.plate}`))].sort(),
    visits: c.jobs.length, total_spent: c.jobs.filter((j) => j.status === 'done').reduce((t, j) => t + j.bill, 0),
    last_visit: day(c.jobs.map((j) => j.created_at).sort().at(-1)), open_jobs: c.jobs.filter((j) => j.status === 'open').map((j) => j.id),
  }))
  if (q) {
    const n = q.trim().toLowerCase()
    out = out.filter((c) => c.name.toLowerCase().includes(n) || c.phone.replace(/\D/g, '').includes(q.replace(/\D/g, '') || '~') || c.vehicles.some((v) => v.toLowerCase().replace(/ /g, '').includes(n.replace(/ /g, ''))))
  }
  return out.sort((a, b) => b.last_visit.localeCompare(a.last_visit))
}

export function customerDetail(s, id) {
  const c = customers(s).find((x) => x.id === id)
  if (!c) return null
  return { ...c, jobs: jobRows(s).filter((r) => r.customer_id === id) }
}

export function vehicles(s, q = '') {
  const byPlate = {}
  for (const j of Object.values(s.jobs)) (byPlate[j.plate] ||= []).push(j)
  let out = Object.entries(byPlate).map(([plate, visits]) => {
    visits.sort((a, b) => b.created_at.localeCompare(a.created_at))
    const last = visits[0]
    return {
      plate, vehicle: last.vehicle, owner: last.owner, visits: visits.length, last_visit: day(last.created_at), last_work: last.complaint,
      last_parts: last.parts.map((p) => p.name), total_spent: visits.filter((j) => j.status === 'done').reduce((t, j) => t + j.bill, 0),
      in_now: visits.some((j) => j.status === 'open'),
    }
  })
  if (q) {
    const plate = q.toUpperCase().replace(/[^A-Z0-9]/g, '')
    const n = q.trim().toLowerCase()
    out = out.filter((v) => (plate && v.plate.includes(plate)) || v.vehicle.toLowerCase().includes(n) || v.owner.toLowerCase().includes(n))
  }
  return out.sort((a, b) => b.last_visit.localeCompare(a.last_visit))
}

export function vehicleDetail(s, plate) {
  const p = plate.toUpperCase().replace(/[^A-Z0-9]/g, '')
  const v = vehicles(s).find((x) => x.plate === p)
  if (!v) return null
  const history = Object.values(s.jobs).filter((j) => j.plate === p).sort((a, b) => b.created_at.localeCompare(a.created_at))
    .map((j) => ({ ...row(j, s.now), complaint: j.complaint, parts_fitted: j.parts.map((x) => x.name) }))
  return { ...v, history }
}

export function staff(s, period = 'week') {
  if (!['today', 'week', 'month'].includes(period)) period = 'week'
  const today = day(s.now)
  const [from, to] = periodRange(period, today)
  const days = []
  for (let d = from; d <= to; d = addDays(d, 1)) days.push(d)
  const mechanics = (s.mechanics || []).map((m) => {
    const theirs = Object.values(s.jobs).filter((j) => j.mechanic_uid === m.uid)
    const closed = theirs.filter((j) => j.status === 'done' && j.closed_at)
    const finished = (a, b) => closed.filter((j) => day(j.closed_at) >= a && day(j.closed_at) <= b)
    const inPeriod = finished(from, to)
    const mine = s.audit.filter((a) => a.by_uid === m.uid)
    return {
      uid: m.uid, name: m.name, phone: m.phone || '', active: m.active !== false,
      finished: { today: finished(today, today).length, week: finished(...periodRange('week', today)).length, month: finished(...periodRange('month', today)).length },
      open_now: theirs.filter((j) => j.status === 'open').length,
      average_minutes: inPeriod.length ? Math.round(inPeriod.reduce((t, j) => t + minutesTaken(j, s.now), 0) / inPeriod.length) : 0,
      revenue: inPeriod.reduce((t, j) => t + j.bill, 0),
      parts_logged: inPeriod.reduce((t, j) => t + j.parts.filter((p) => !p.consumable).reduce((n, p) => n + p.qty, 0), 0),
      last_active: mine[0]?.at || closed.map((j) => j.closed_at).sort().at(-1) || '',
      per_day: days.map((d) => ({ day: d, jobs: finished(d, d).length })),
    }
  })
  return { period, from, to, mechanics, count: mechanics.filter((m) => m.active).length }
}
