import { describe, expect, it } from 'vitest'
import { BAY_X, BAYS, layout, stationFor, STATIONS, WASH_X } from './layout.js'

const job = (id, stage, extra = {}) => ({ id, stage, status: 'open', vehicle: 'Splendor Plus', plate: 'MH12AB1234',
  owner: 'Ramesh', mechanic_name: 'Raju', stage_started_at: `2026-10-13T0${id.slice(-1)}:00:00Z`, ...extra })

describe('stationFor', () => {
  it('maps each job stage to a place on the floor', () => {
    expect(stationFor(job('J-1', 'intake'))).toBe('door')
    expect(stationFor(job('J-1', 'washing'))).toBe('wash')
    expect(stationFor(job('J-1', 'service'))).toBe('service')
    expect(stationFor(job('J-1', 'waiting_approval'))).toBe('service')
    expect(stationFor(job('J-1', 'ready'))).toBe('delivery')
    expect(stationFor(job('J-1', 'done', { status: 'done' }))).toBe('delivered')
  })
})

describe('layout', () => {
  it('places vehicles, flags pending quotes and counts every station', () => {
    const plan = layout({
      jobs: [job('J-1', 'intake', { mechanic_name: '' }), job('J-2', 'washing', { mechanic_name: 'Salim', vehicle: 'Activa 6G' }),
        job('J-3', 'service'), job('J-4', 'ready'), job('J-5', 'done', { status: 'done' })],
      pending_approvals: [{ id: 'Q-1', job_id: 'J-3', total: 1450 }],
    })
    expect(plan.vehicles.map((v) => [v.id, v.station])).toEqual([['J-1', 'door'], ['J-2', 'wash'], ['J-3', 'service'], ['J-4', 'delivery']])
    expect(plan.vehicles.find((v) => v.id === 'J-2').kind).toBe('scooter')
    expect(plan.vehicles.find((v) => v.id === 'J-3').alert).toBe('approval')
    expect(plan.counts).toEqual({ door: 1, wash: 1, service: 1, waiting: 1, delivery: 1, delivered: 1 })
  })

  it('puts a mechanic next to the vehicle they touched last, once', () => {
    const plan = layout({ jobs: [job('J-1', 'service'), job('J-2', 'service')], pending_approvals: [] })
    expect(plan.mechanics).toHaveLength(1)
    expect(plan.mechanics[0]).toMatchObject({ name: 'Raju', jobId: 'J-2', busy: true })
  })

  it('parks extra service jobs in front of the lifts when all bays are busy', () => {
    const jobs = Array.from({ length: BAYS + 2 }, (_, i) => job(`J-${i + 1}`, 'service', { mechanic_name: `M${i}` }))
    const plan = layout({ jobs, pending_approvals: [] })
    expect(plan.overflow).toBe(2)
    const z = new Set(plan.vehicles.filter((v) => v.slot >= BAYS).map((v) => v.z))
    expect(z.size).toBe(1)
    expect(plan.vehicles.filter((v) => v.slot < BAYS).every((v) => v.z < 0)).toBe(true)
  })

  it('handles an empty garage', () => {
    expect(layout({ jobs: [], pending_approvals: [] }).vehicles).toEqual([])
    expect(layout(null).counts.door).toBe(0)
  })
})

describe('layout: mechanics follow their latest job', () => {
  it('moves the mechanic to the job that changed stage most recently, wherever it is', () => {
    const plan = layout({ jobs: [job('J-1', 'service'), job('J-2', 'washing')], pending_approvals: [] })
    expect(plan.mechanics).toEqual([expect.objectContaining({ name: 'Raju', jobId: 'J-2' })])
  })
})

describe('floor order (C10: washing comes last, just before delivery)', () => {
  it('runs front door → service bays → wash bay → delivery from left to right', () => {
    expect(STATIONS.map((s) => s.key)).toEqual(['door', 'service', 'wash', 'delivery'])
    for (let i = 1; i < STATIONS.length; i++) expect(STATIONS[i].x0).toBeGreaterThan(STATIONS[i - 1].x1)
    const wash = STATIONS.find((s) => s.key === 'wash')
    const service = STATIONS.find((s) => s.key === 'service')
    expect(WASH_X).toBeGreaterThan(wash.x0)
    expect(WASH_X).toBeLessThan(wash.x1)
    for (let i = 0; i < BAYS; i++) expect(BAY_X(i)).toBeGreaterThan(service.x0) && expect(BAY_X(i)).toBeLessThan(service.x1)
    const plan = layout({ jobs: [job('J-1', 'intake'), job('J-2', 'service'), job('J-3', 'washing'), job('J-4', 'ready')], pending_approvals: [] })
    const x = ['J-1', 'J-2', 'J-3', 'J-4'].map((id) => plan.vehicles.find((v) => v.id === id).x)
    expect(x).toEqual([...x].sort((a, b) => a - b))
  })
})
