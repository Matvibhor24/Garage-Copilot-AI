import { beforeEach, describe, expect, it, vi } from 'vitest'
import { langParam, LANGS, readLang, saveLang } from './lang.js'

describe('reply language picker (C11)', () => {
  beforeEach(() => {
    const data = new Map()
    vi.stubGlobal('localStorage', { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, String(v)) })
  })

  it('offers Auto, English, Hindi and Marathi, Auto by default, remembered per device and screen', () => {
    expect(LANGS.map((l) => l.label)).toEqual(['Auto', 'English', 'हिंदी', 'मराठी'])
    expect(readLang('mechanic')).toBe('auto')
    saveLang('mechanic', 'mr')
    expect(readLang('mechanic')).toBe('mr')
    expect(readLang('owner')).toBe('auto')
    localStorage.setItem('gc.lang.owner', 'xx')
    expect(readLang('owner')).toBe('auto')
  })

  it('only known languages reach the gateway', () => {
    expect(langParam('hi')).toBe('&lang=hi')
    expect(langParam('auto')).toBe('')
    expect(langParam('fr')).toBe('')
  })
})
