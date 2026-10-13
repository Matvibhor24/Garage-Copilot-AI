import { describe, expect, it } from 'vitest'
import { handle } from './server.js'
import * as store from './store.js'
import { scriptLine } from './voice.js'

function play(i) {
  store.change((s) => {
    const line = scriptLine(i)
    s.now = store.at(line.time)
    line.run(s)
  })
}

describe('demo backend replays the demo job', () => {
  it('runs intake to close with the customer approving in between', async () => {
    store.reset()
    for (const i of [0, 1, 2, 3, 4]) play(i)
    let view = await handle('GET', '/api/j/demo-J-1042')
    expect(view.timeline.map((t) => t.label)).toEqual(['Checked in', 'Washing', 'In service'])
    expect(view.timeline[1].minutes).toBe(18)
    expect(view.quotes[0]).toMatchObject({ id: 'Q-77', total: 950, status: 'pending' })

    let dash = await handle('GET', '/api/owner/dashboard')
    expect(dash.pending_approvals).toHaveLength(1)

    store.change((s) => { s.now = store.at('11:07') })
    expect((await handle('POST', '/api/j/demo-J-1042/quotes/Q-77/approve')).status).toBe('approved')
    expect(store.get().messages.find((m) => m.to === 'm-raju').text).toBe('Ramesh approved. Go ahead.')

    play(5)
    play(6)
    view = await handle('GET', '/api/j/demo-J-1042')
    expect(view.stage_label).toBe('Ready for pickup')
    expect(view.bill).toBe(950)

    dash = await handle('GET', '/api/owner/dashboard')
    expect(dash.revenue_today).toBe(12400)
    expect(dash.open_jobs).toBe(5)
    expect(dash.low_stock).toEqual([{ part_id: 'clutch-splendor', name: 'Clutch plate set', qty: 1 }])
    expect(dash.reorder_asks[0].text).toBe('Clutch plate set down to 1. Reorder 5 from Sai Spares?')

    await handle('POST', '/api/owner/inventory/clutch-splendor/reorder', {})
    dash = await handle('GET', '/api/owner/dashboard')
    expect(dash.reorder_asks).toEqual([])
  })

  it('answers the owner from the demo data, and the owner can reorder by voice', () => {
    store.reset()
    for (const i of [0, 1, 2, 3, 4]) play(i)
    store.change((s) => { s.now = store.at('11:07') })
    store.change((s) => store.decideQuote(s, 'Q-77', 'approved'))
    play(5)
    play(6)
    const ask = (i) => {
      let out
      store.change((s) => { out = scriptLine(i, 'owner').run(s) })
      return out.reply
    }
    expect(ask(0)).toMatch(/^5 open jobs/)
    expect(ask(1)).toBe('Nothing is waiting for a customer right now.')
    expect(ask(2)).toBe('₹12,400 from 3 closed jobs today.')
    expect(ask(3)).toContain('Clutch plate set for Splendor: 1 left')
    expect(ask(4)).toMatch(/^J-1042 took .* from check-in to ready\.$/)
    expect(ask(5)).toBe('Done. Ordered 5 clutch plate set from Sai Spares.')
    expect(Object.values(store.get().reorder_asks).filter((a) => a.status === 'asked')).toEqual([])
    expect(ask(5)).toBe("There's no reorder question open right now.")
  })

  it('ends with a manual lookup that says its answer is made up', () => {
    store.reset()
    let out
    store.change((s) => { out = scriptLine(7).run(s) })
    expect(out.tools[0][0]).toBe('lookup_manual')
    expect(out.reply).toMatch(/^Demo answer, not a real spec/)
    expect(store.get().audit[0]).toMatchObject({ action: 'lookup_manual', details: { found: true, source: 'Demo manual p.12' } })
  })

  it('checks the PIN and rejects unknown links', async () => {
    await expect(handle('POST', '/api/auth/pin', { garage_id: 'shree-auto', name: 'Raju', pin: '0000' })).rejects.toThrow('Wrong name or PIN')
    expect((await handle('POST', '/api/auth/pin', { garage_id: 'shree-auto', name: 'raju', pin: '1234' })).claims.name).toBe('Raju')
    await expect(handle('GET', '/api/j/forged')).rejects.toThrow('invalid')
  })
})
