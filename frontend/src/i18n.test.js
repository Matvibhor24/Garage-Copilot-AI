import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { STRINGS, t, textIn } from './i18n.js'

describe('customer page strings (C12)', () => {
  it('has a Hindi string for every English key, and nothing extra', () => {
    const missing = Object.keys(STRINGS.en).filter((k) => !STRINGS.hi[k]?.trim())
    expect(missing).toEqual([])
    expect(Object.keys(STRINGS.hi).sort()).toEqual(Object.keys(STRINGS.en).sort())
  })

  it('keeps the same placeholders in both languages', () => {
    const vars = (s) => (s.match(/\{\w+\}/g) || []).sort()
    for (const k of Object.keys(STRINGS.en)) expect([k, vars(STRINGS.hi[k])]).toEqual([k, vars(STRINGS.en[k])])
  })

  it('fills placeholders and picks the text in the chosen language', () => {
    expect(t('en', 'approveAmount', { amount: '₹950' })).toBe('Approve ₹950')
    expect(t('hi', 'approveAmount', { amount: '₹950' })).toBe('₹950 मंज़ूर करें')
    const q = { text: 'मराठी', text_en: 'Hi Ramesh', text_hi: 'नमस्ते Ramesh' }
    expect(textIn('en', q)).toBe('Hi Ramesh')
    expect(textIn('hi', q)).toBe('नमस्ते Ramesh')
    expect(textIn('hi', { text: 'old quote' })).toBe('old quote') // quotes sent before C12
  })

  it('the customer page uses only dictionary keys that exist', () => {
    const src = readFileSync(new URL('./screens/Customer.jsx', import.meta.url), 'utf8')
    const used = [...src.matchAll(/\btr\('([\w.]+)'/g)].map((m) => m[1])
    expect(used.length).toBeGreaterThan(20)
    expect(used.filter((k) => !(k in STRINGS.en))).toEqual([])
  })
})
