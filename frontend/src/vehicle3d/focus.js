// What the 3D view should show for a job: which vehicle, which part zone to light up, and why.
// Pure functions (no three.js) so they are cheap to test and to import anywhere.

const SCOOTERS = ['activa', 'jupiter', 'access', 'dio', 'ntorq', 'scooty', 'pleasure', 'maestro', 'fascino',
  'burgman', 'vespa', 'ather', 'chetak', 'ola', 'aerox', 'rayzr', 'ray zr', 'avenis', 'iqube', 'zest', 'destini']
const CARS = ['swift', 'dzire', 'i20', 'i10', 'alto', 'wagonr', 'wagon r', 'baleno', 'creta', 'venue', 'nexon',
  'brezza', 'ertiga', 'innova', 'city', 'amaze', 'verna', 'seltos', 'sonet', 'scorpio', 'thar', 'xuv', 'kwid',
  'tiago', 'punch', 'celerio', 'eeco', 'fortuner', 'polo', 'vento', 'car']

// "motorcycle" | "scooter" | null (cars and unknown four-wheelers get no 3D view)
export function vehicleKind(vehicle = '') {
  const v = ` ${vehicle.toLowerCase()} `
  if (SCOOTERS.some((w) => v.includes(w))) return 'scooter'
  if (CARS.some((w) => v.includes(` ${w}`))) return null
  return 'motorcycle'
}

// Part zones the models know how to light up, with the words that point at them (part ids, names, complaints).
// Order matters: the first match wins, so specific words come before general ones.
const ZONES = [
  ['cvt', 'Drive belt', ['drive belt', 'drive-belt', 'variator', 'roller', 'cvt', 'pulley']],
  ['clutch', 'Clutch', ['clutch']],
  ['brakes', 'Brakes', ['brake', 'disc', 'pad']],
  ['chain', 'Chain & sprockets', ['chain', 'sprocket', 'lube']],
  ['air_filter', 'Air filter', ['air filter', 'air-filter']],
  ['battery', 'Battery', ['battery', 'self start', 'not starting']],
  ['spark_plug', 'Spark plug', ['spark', 'plug', 'misfir']],
  ['carburettor', 'Carburettor', ['carb', 'carburettor', 'carburetor', 'pickup', 'idling']],
  ['tyres', 'Tyres', ['tyre', 'tire', 'tube', 'puncture', 'wheel']],
  ['suspension', 'Suspension', ['fork', 'shock', 'suspension', 'oil seal']],
  ['lights', 'Lights', ['bulb', 'headlight', 'head light', 'indicator', 'tail lamp', 'light']],
  ['horn', 'Horn', ['horn']],
  ['mirrors', 'Mirrors', ['mirror']],
  ['cables', 'Cables', ['cable', 'accelerator', 'throttle']],
  ['engine', 'Engine', ['engine oil', 'oil filter', 'gear oil', 'oil', 'coolant', 'engine', 'service', 'noise']],
]

export const ZONE_LABELS = Object.fromEntries(ZONES.map(([key, label]) => [key, label]))

// "Clutch plate set" / "clutch-splendor" / "clutch slipping" -> "clutch"
export function zoneFor(text = '') {
  const t = text.toLowerCase()
  for (const [key, , words] of ZONES) if (words.some((w) => t.includes(w))) return key
  return null
}

const STAGE_TEXT = {
  intake: 'Checked in',
  washing: 'Getting washed',
  service: 'Being serviced',
  waiting_approval: 'Waiting for your OK',
  ready: 'Ready for pickup',
  done: 'Ready for pickup',
}

/**
 * What to show for one job. Accepts the customer view (/api/j/:token) or an owner job (+ its pending quote).
 * Priority for the part in focus: pending quote > latest part fitted > the complaint.
 * Returns { kind, stage, zones: [zone...], focus: zone|null, title, detail }.
 */
export function scene({ vehicle, stage, status, quotes = [], parts = [], complaint = '' } = {}) {
  const done = status === 'done' || stage === 'done'
  const pending = quotes.find((q) => q.status === 'pending')
  const st = done ? 'done' : pending ? 'waiting_approval' : stage || 'intake'

  const named = (list) => [...new Set(list.map((n) => zoneFor(n)).filter(Boolean))]
  let zones = []
  let reason = ''
  if (pending) {
    zones = named(pending.lines.map((l) => `${l.part_id || ''} ${l.name}`))
    reason = pending.lines.map((l) => l.name).join(', ')
  }
  if (!zones.length && parts.length) {
    const last = parts[parts.length - 1]
    zones = named([`${last.part_id || ''} ${last.name}`])
    reason = last.name
  }
  if (!zones.length && complaint) {
    zones = named(complaint.split(/[,;]+/))
    reason = complaint
  }
  const focus = zones[0] || null

  let detail = ''
  if (st === 'waiting_approval') detail = `Needs your OK: ${reason}`
  else if (st === 'washing') detail = 'Foam, rinse and shine'
  else if (st === 'done') detail = 'All done. See you soon!'
  else if (focus) detail = `${st === 'intake' ? 'To check' : 'Working on'}: ${ZONE_LABELS[focus]}`

  return { kind: vehicleKind(vehicle), stage: st, zones, focus, title: STAGE_TEXT[st] || st, detail }
}
