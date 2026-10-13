import { describe, expect, it } from 'vitest'
import { scene, vehicleKind, zoneFor } from './focus.js'

describe('vehicleKind', () => {
  it('picks the model from the vehicle name', () => {
    expect(vehicleKind('Splendor Plus')).toBe('motorcycle')
    expect(vehicleKind('Pulsar 150')).toBe('motorcycle')
    expect(vehicleKind('Honda Activa 6G')).toBe('scooter')
    expect(vehicleKind('TVS Jupiter')).toBe('scooter')
    expect(vehicleKind('Maruti Swift')).toBe(null)
    expect(vehicleKind('Hyundai i20')).toBe(null)
  })
})

describe('zoneFor', () => {
  it('maps part ids, part names and complaints to a zone', () => {
    expect(zoneFor('clutch-splendor Clutch plate set')).toBe('clutch')
    expect(zoneFor('Brake shoe set')).toBe('brakes')
    expect(zoneFor('Chain sprocket kit')).toBe('chain')
    expect(zoneFor('Drive belt')).toBe('cvt')
    expect(zoneFor('Engine oil 1L 10W30')).toBe('engine')
    expect(zoneFor('Front fork oil seal')).toBe('suspension')
    expect(zoneFor('Air filter')).toBe('air_filter')
    expect(zoneFor('clutch slipping')).toBe('clutch')
    expect(zoneFor('nothing we know')).toBe(null)
  })
})

describe('scene', () => {
  const quote = { status: 'pending', lines: [{ part_id: 'clutch-splendor', name: 'Clutch plate set' }] }

  it('a pending quote wins and puts the job in waiting_approval', () => {
    const s = scene({ vehicle: 'Splendor Plus', stage: 'service', status: 'open', quotes: [quote],
      parts: [{ name: 'Engine oil 1L 10W30' }], complaint: 'clutch slipping' })
    expect(s).toMatchObject({ kind: 'motorcycle', stage: 'waiting_approval', focus: 'clutch' })
    expect(s.detail).toBe('Needs your OK: Clutch plate set')
  })

  it('falls back to the latest part fitted, then the complaint', () => {
    expect(scene({ vehicle: 'Activa', stage: 'service', parts: [{ name: 'Drive belt' }] }).focus).toBe('cvt')
    expect(scene({ vehicle: 'Splendor', stage: 'intake', complaint: 'clutch slipping, general service' }))
      .toMatchObject({ focus: 'clutch', zones: ['clutch', 'engine'], detail: 'To check: Clutch' })
  })

  it('shows washing and done as their own stages', () => {
    expect(scene({ vehicle: 'Splendor', stage: 'washing' })).toMatchObject({ stage: 'washing', title: 'Getting washed' })
    expect(scene({ vehicle: 'Splendor', stage: 'done', status: 'done' })).toMatchObject({ stage: 'done', title: 'Ready for pickup' })
  })
})
