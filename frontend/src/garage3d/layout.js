// Where everything stands on the owner's 3D garage floor, from the dashboard data. Pure (no three.js), so it is
// cheap to test. Units are metres on the floor: x runs left (front door) to right (delivery), z towards the viewer.
import { vehicleKind } from '../vehicle3d/focus.js'

// The floor plan, in the order a vehicle moves through the garage: front door, service bays, then the wash bay just
// before delivery (garages wash after the repair, C10).
export const STATIONS = [
  { key: 'door', label: 'Front door', hint: 'Waiting to start', x0: -13, x1: -8.6 },
  { key: 'service', label: 'Service bays', hint: 'On the lifts', x0: -8.2, x1: 2.8 },
  { key: 'wash', label: 'Wash bay', hint: 'Foam and rinse', x0: 3.2, x1: 7.8 },
  { key: 'delivery', label: 'Delivery', hint: 'Ready for pickup', x0: 8.2, x1: 13 },
]
export const FLOOR = { x0: -13, x1: 13, z0: -5.2, z1: 4.6 }
export const BAYS = 3
export const BAY_X = (i) => -6.35 + i * 3.4 // centre of service bay i
export const WASH_X = 5.5 // the wash arch, between the service bays and delivery
const ROW_Z = [-3, -1, 1, 3] // parking rows at the door and delivery (vehicles side by side)

// Job stage -> station. A pending quote keeps the vehicle on its lift, flagged.
export function stationFor(job) {
  if (job.status === 'done' || job.stage === 'done') return 'delivered'
  if (job.stage === 'intake') return 'door'
  if (job.stage === 'washing') return 'wash'
  if (job.stage === 'ready') return 'delivery'
  return 'service' // service, waiting_approval
}

const byStart = (a, b) => String(a.stage_started_at || '').localeCompare(String(b.stage_started_at || ''))

/**
 * dash: the owner dashboard ({ jobs, pending_approvals, low_stock }).
 * Returns { vehicles, mechanics, counts, overflow }:
 *  vehicles:  [{ id, kind, vehicle, plate, station, slot, x, z, alert, mechanic }] (delivered jobs are not placed)
 *  mechanics: [{ name, jobId, x, z, busy }] one per mechanic on a vehicle at the wash bay or on a lift
 *  counts:    { door, wash, service, waiting, delivery, delivered }
 */
export function layout(dash) {
  const jobs = dash?.jobs || []
  const pending = new Set((dash?.pending_approvals || []).map((q) => q.job_id))
  const groups = { door: [], wash: [], service: [], delivery: [], delivered: [] }
  for (const j of [...jobs].sort(byStart)) groups[stationFor(j)].push(j)

  const vehicles = []
  const place = (j, station, slot, x, z) => vehicles.push({
    id: j.id, since: j.stage_started_at || '', kind: vehicleKind(j.vehicle) || 'car', vehicle: j.vehicle, plate: j.plate, owner: j.owner, station, slot, x, z,
    alert: pending.has(j.id) || j.stage === 'waiting_approval' ? 'approval' : null, mechanic: j.mechanic_name || '',
  })
  const parkRow = (list, station, cx) => list.forEach((j, i) => {
    // Four rows side by side, then a second column further out
    place(j, station, i, cx + (i >= ROW_Z.length ? (station === 'door' ? -2.2 : 2.2) : 0), ROW_Z[i % ROW_Z.length])
  })

  parkRow(groups.door, 'door', -10.6)
  groups.wash.forEach((j, i) => place(j, 'wash', i, WASH_X, ROW_Z[[1, 2, 0, 3][i % 4]]))
  const onLifts = groups.service.slice(0, BAYS)
  const waitingForLift = groups.service.slice(BAYS)
  onLifts.forEach((j, i) => place(j, 'service', i, BAY_X(i), -1.2))
  waitingForLift.forEach((j, i) => place(j, 'service', BAYS + i, BAY_X(0) + i * 2.6, 3.4)) // parked in front of the lifts
  parkRow(groups.delivery, 'delivery', 10.6)

  // A mechanic stands by the vehicle they touched most recently (wash bay or lift)
  const mechanics = []
  const seen = new Set()
  const latest = (a, b) => b.since.localeCompare(a.since) || (b.station === 'service') - (a.station === 'service')
  for (const v of [...vehicles].sort(latest)) {
    if (!v.mechanic || seen.has(v.mechanic) || !['wash', 'service'].includes(v.station)) continue
    seen.add(v.mechanic)
    mechanics.push({ name: v.mechanic, jobId: v.id, x: v.x + 0.55, z: v.z + 1.15, busy: v.slot < BAYS || v.station === 'wash' })
  }

  return {
    vehicles,
    mechanics,
    overflow: waitingForLift.length,
    counts: {
      door: groups.door.length,
      wash: groups.wash.length,
      service: groups.service.length,
      waiting: vehicles.filter((v) => v.alert === 'approval').length,
      delivery: groups.delivery.length,
      delivered: groups.delivered.length,
    },
  }
}
