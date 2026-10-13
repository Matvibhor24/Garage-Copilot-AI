import { describe, expect, it } from 'vitest'
import { actionDetail, ago, clock, minutes, plate, rupees } from './format.js'

describe('format', () => {
  it('formats money, plates and durations', () => {
    expect(rupees(12400)).toBe('₹12,400')
    expect(rupees(125000)).toBe('₹1,25,000')
    expect(plate('MH12AB1234')).toBe('MH 12 AB 1234')
    expect(minutes(18)).toBe('18 min')
    expect(minutes(95)).toBe('1 h 35 min')
  })
  it('shows IST times whatever the device timezone', () => {
    expect(clock('2026-10-14T05:11:00Z')).toBe('10:41')
  })
  it('describes relative times and audit entries', () => {
    expect(ago('2026-10-14T05:00:00Z', Date.parse('2026-10-14T05:10:00Z'))).toBe('10 min ago')
    expect(actionDetail({ action: 'close_job', details: { job_id: 'J-1042', bill: 950 } })).toBe('J-1042 · bill ₹950')
  })
})

describe('manual lookups in the activity feed', () => {
  it('shows the question and the source, or that it is not in the manual', () => {
    const entry = (details) => ({ action: 'lookup_manual', details })
    expect(actionDetail(entry({ question: 'clutch free play', vehicle: 'Splendor Plus', found: true, source: "Splendor Plus owner's manual p.42" })))
      .toBe("clutch free play (Splendor Plus owner's manual p.42)")
    expect(actionDetail(entry({ question: 'wiper blade', vehicle: 'Splendor Plus', found: false, source: '' })))
      .toBe('wiper blade (Splendor Plus: not in the manual)')
  })
})
