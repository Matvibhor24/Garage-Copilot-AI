import { describe, expect, it } from 'vitest'
import { actionDetail, actionLabel, ago, clock, minutes, plate, rupees } from './format.js'

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

describe('settings and auto-approved quotes in the activity feed (C09)', () => {
  it('says what changed and that a quote was approved automatically', () => {
    expect(actionLabel('update_settings')).toBe('changed settings')
    expect(actionDetail({ action: 'update_settings', details: { summary: 'changed the auto-approve limit from ₹500 to ₹0' } }))
      .toBe('the auto-approve limit from ₹500 to ₹0')
    expect(actionDetail({ action: 'send_quote', details: { quote_id: 'Q-77', total: 400, auto: true, quote_limit: 500 } }))
      .toBe('Q-77 · ₹400 · approved automatically (within the ₹500 limit)')
    expect(actionDetail({ action: 'send_quote', details: { quote_id: 'Q-77', total: 950, reason: '₹950 > ₹500 limit' } }))
      .toBe('Q-77 · ₹950 · ₹950 > ₹500 limit')
  })
})

describe('web searches in the feed (C14)', () => {
  it('shows the question and the sites', () => {
    expect(actionLabel('web_search_fixes')).toBe('searched the web')
    expect(actionDetail({ action: 'web_search_fixes', details: { question: 'hard start', sites: ['a.example', 'b.example'] } }))
      .toBe('hard start (web · a.example, b.example)')
  })
})

describe('Model Armor flags in the activity feed (C18)', () => {
  it('says what was flagged, where, and what was done', () => {
    expect(actionLabel('armor_flagged')).toBe('AI safety: flagged by Model Armor')
    expect(actionDetail({ action: 'armor_flagged', details: { where: 'caller', reasons: ['pi_and_jailbreak'], action: 'call ended' } }))
      .toBe('caller · pi_and_jailbreak · call ended')
    expect(actionDetail({ action: 'armor_flagged', details: { where: 'web search', reasons: [], action: 'results dropped' } }))
      .toBe('web search · results dropped')
  })
})
