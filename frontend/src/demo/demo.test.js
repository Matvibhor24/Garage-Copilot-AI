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
    for (const i of [0, 1, 2, 3]) play(i) // intake, service, stock check, quote
    let view = await handle('GET', '/api/j/demo-J-1042')
    expect(view.timeline.map((t) => t.label)).toEqual(['Checked in', 'In service'])
    expect(view.timeline[0].minutes).toBe(18)
    expect(view.quotes[0]).toMatchObject({ id: 'Q-77', total: 950, status: 'pending' })

    let dash = await handle('GET', '/api/owner/dashboard')
    expect(dash.pending_approvals).toHaveLength(1)

    store.change((s) => { s.now = store.at('11:07') })
    expect((await handle('POST', '/api/j/demo-J-1042/quotes/Q-77/approve')).status).toBe('approved')
    expect(store.get().messages.find((m) => m.to === 'm-raju').text).toBe('Ramesh approved. Go ahead.')

    play(4) // used one clutch plate
    play(5) // washing comes after the repair (C10)
    view = await handle('GET', '/api/j/demo-J-1042')
    expect(view.timeline.map((t) => t.label)).toEqual(['Checked in', 'In service', 'Washing'])
    expect(view.timeline[1].minutes).toBe(85)
    play(6) // job done
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
    for (const i of [0, 1, 2, 3]) play(i)
    store.change((s) => { s.now = store.at('11:07') })
    store.change((s) => store.decideQuote(s, 'Q-77', 'approved'))
    play(4)
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
    expect(ask(6)).toBe('Parts and fittings on J-1042 cost us ₹520. The bill is ₹950, so the margin is ₹430.')
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

describe('owner settings (C09)', () => {
  it('validates, saves with an audit line, and the next quote uses the new limit', async () => {
    store.reset()
    const before = await handle('GET', '/api/owner/settings')
    expect(before).toMatchObject({ quote_limit: 500, name: 'Shree Auto', supplier: 'Sai Spares', low_at: 1 })
    await expect(handle('PUT', '/api/owner/settings', { changes: { quote_limit: -1 } })).rejects.toThrow('between 0 and 1,00,000')
    await expect(handle('PUT', '/api/owner/settings', { changes: { quote_limit: '9.5' } })).rejects.toThrow('whole number')
    const out = await handle('PUT', '/api/owner/settings', { changes: { quote_limit: '1000' } })
    expect(out.summary).toBe('changed the auto-approve limit from ₹500 to ₹1000')
    expect(store.get().audit[0]).toMatchObject({ action: 'update_settings', by_name: 'Asha' })

    for (const i of [0, 1, 2, 3]) play(i) // ₹950 quote, now within the ₹1,000 limit
    const view = await handle('GET', '/api/j/demo-J-1042')
    expect(view.quotes[0]).toMatchObject({ status: 'approved', auto: true, quote_limit: 1000 })
    expect(store.get().messages.some((m) => m.kind === 'quote')).toBe(false) // never reached the customer
    expect(store.get().audit.find((a) => a.action === 'send_quote').details.auto).toBe(true)
  })
})

describe('consumables (C13)', () => {
  it('fitting a clutch plate also uses its fittings; cost and margin add up', async () => {
    store.reset()
    for (const i of [0, 1, 2, 3]) play(i)
    store.change((s) => { s.now = store.at('11:07') })
    store.change((s) => store.decideQuote(s, 'Q-77', 'approved'))
    const before = store.get().inventory['bolt-m6'].qty
    play(4)
    const s = store.get()
    expect(before - s.inventory['bolt-m6'].qty).toBe(4)
    const j = s.jobs['J-1042']
    expect(j.parts.map((p) => p.name)).toEqual(['Clutch plate set']) // the clutch fittings are the garage's own cost
    expect(j.consumables.map((c) => c.name)).toEqual(['Clutch cover gasket', 'M6 bolt', 'M6 washer', 'Grease (10 g)'])
    expect(store.money(j)).toMatchObject({ parts: 650, consumables: 0, labour: 300, bill: 950, cost: 455 + 45 + 8 + 4 + 8 })
    for (const seeded of ['J-1039', 'J-1038', 'J-1036']) expect(store.money(s.jobs[seeded]).bill).toBe(s.jobs[seeded].bill)
    const dash = await handle('GET', '/api/owner/dashboard')
    expect(dash.jobs.find((x) => x.id === 'J-1042').money.margin).toBe(950 - 520)
  })
})

describe('manual first, then the web with an OK (C14)', () => {
  it('asks before searching, then gives made-up demo fixes labelled as web results', () => {
    store.reset()
    let out
    store.change((s) => { out = scriptLine(8).run(s) })
    expect(out.tools[0]).toEqual(['lookup_manual', expect.objectContaining({ found: false })])
    expect(out.reply).toMatch(/isn't in the manual\. Shall I search online for known causes and fixes\?$/)
    store.change((s) => { out = scriptLine(9).run(s) })
    expect(scriptLine(9).say).toMatch(/^Yes/)
    expect(out.tools[0][0]).toBe('web_search_fixes')
    expect(out.reply).toMatch(/^From the web, not the manual, and these demo answers are made up/)
    expect(store.get().audit[0]).toMatchObject({ action: 'web_search_fixes' })
  })
})

describe('AI front desk call (C15)', () => {
  it('a verified caller hears their status; estimate and callback wait for the owner', async () => {
    store.reset()
    for (const i of [0, 1]) play(i) // Ramesh's Splendor is in service
    const started = await handle('POST', '/api/j/demo-J-1042/call')
    expect(started.verified).toBe(true)
    const say = (i) => {
      let out
      store.change((s) => { s.calls[0].heard.push(scriptLine(i, 'caller').say); out = scriptLine(i, 'caller').run(s) })
      return out
    }
    expect(say(0).reply).toBe('Your Splendor Plus is in service right now.')
    const wait = say(1) // "if I bring another bike now?": counts and ranges, nobody's details
    expect(wait.tools[0][0]).toBe('service_wait_time')
    expect(wait.reply).toMatch(/vehicles ahead/)
    expect(wait.reply).not.toMatch(/MH12|Ramesh|Meena|Arjun/)
    expect(say(2).tools[0][1]).toEqual({ sent: true, sent_to: 'the number we have on file' })
    expect(say(3).reply).not.toMatch(/₹/) // the front desk never says a price
    say(4)
    let calls = await handle('GET', '/api/owner/calls')
    expect(calls.calls[0].verified).toBe(true)
    expect(calls.calls[0].summary).toMatch(/^Hello, is my Splendor ready\? · If I bring in another bike/)
    expect(calls.estimates[0]).toMatchObject({ id: 'E-1', total: 1170, status: 'asked' })
    expect(calls.callbacks[0].reason).toBe('the bill')
    expect(store.get().messages.some((m) => m.kind === 'estimate')).toBe(false) // nothing to the caller yet
    await handle('POST', '/api/owner/estimates/E-1/send', {})
    expect(store.get().messages.find((m) => m.kind === 'estimate').text).toContain('about ₹1170')
    await handle('POST', '/api/owner/callbacks/CB-1/done', {})
    calls = await handle('GET', '/api/owner/calls')
    expect(calls.estimates).toEqual([])
    expect(calls.callbacks).toEqual([])
  })

  it('a website caller (not verified) gets no job details', async () => {
    store.reset()
    for (const i of [0, 1]) play(i)
    await expect(handle('POST', '/api/call/start', { phone: '12' })).rejects.toThrow('10-digit')
    await handle('POST', '/api/call/start', { phone: '+91 98111 12222' })
    let out
    store.change((s) => { out = scriptLine(0, 'caller').run(s) })
    expect(out.tools[0][1]).toEqual({ verified: false, jobs: [] })
    expect(out.reply).toMatch(/can't share job details/)
  })
})

describe('owner records (C17)', () => {
  it('jobs: history in the seed, filters, totals, pagination and CSV', async () => {
    store.reset()
    const all = await handle('GET', '/api/owner/jobs')
    expect(all.totals.jobs).toBeGreaterThan(40)
    expect(all.jobs).toHaveLength(50)
    expect(all.next_cursor).toBe('50')
    const rest = await handle('GET', '/api/owner/jobs?cursor=50')
    expect(all.jobs.length + rest.jobs.length).toBe(all.totals.jobs)
    expect(all.jobs.map((j) => j.created_at)).toEqual([...all.jobs.map((j) => j.created_at)].sort().reverse())
    const open = await handle('GET', '/api/owner/jobs?status=open')
    expect(open.jobs.every((j) => j.status === 'open')).toBe(true)
    const salim = await handle('GET', '/api/owner/jobs?mechanic=Salim&status=closed')
    expect(salim.jobs.every((j) => j.mechanic === 'Salim')).toBe(true)
    if (!salim.next_cursor) expect(salim.totals.revenue).toBe(salim.jobs.reduce((t, j) => t + j.bill, 0))
    const one = await handle('GET', '/api/owner/jobs?q=MH14GH7710')
    expect(new Set(one.jobs.map((j) => j.plate))).toEqual(new Set(['MH14GH7710']))
    const csv = await handle('GET', '/api/owner/jobs.csv?status=open')
    const lines = csv.trim().split('\r\n')
    expect(lines[0]).toBe('date,job_id,vehicle,plate,customer,mechanic,status,parts,consumables,labour,bill,cost,margin,minutes,closed_at')
    expect(lines).toHaveLength(open.totals.jobs + 1)
    const d = await handle('GET', '/api/owner/jobs/J-1038')
    expect(d.money.bill).toBe(6600)
  })

  it('customers, vehicles and staff; a switched-off mechanic cannot sign in', async () => {
    store.reset()
    const customers = await handle('GET', '/api/owner/customers')
    const vikas = customers.find((c) => c.name === 'Vikas')
    expect(vikas.visits).toBeGreaterThan(1)
    expect((await handle('GET', '/api/owner/customers?q=vik')).map((c) => c.name)).toEqual(['Vikas'])
    const v = await handle('GET', '/api/owner/vehicles/MH14GH7710')
    expect(v.history[0].job_id).toBe('J-1038')
    const staff = await handle('GET', '/api/owner/staff?period=month')
    expect(staff.mechanics.map((m) => m.name)).toEqual(['Raju', 'Salim'])
    expect(staff.mechanics[0].per_day.length).toBeGreaterThan(0)
    await handle('POST', '/api/owner/mechanics/m-raju/deactivate', {})
    await expect(handle('POST', '/api/auth/pin', { garage_id: 'shree-auto', name: 'Raju', pin: '1234' })).rejects.toThrow('switched off')
    await handle('POST', '/api/owner/mechanics', { name: 'Deepak', pin: '4321' })
    expect((await handle('POST', '/api/auth/pin', { garage_id: 'shree-auto', name: 'Deepak', pin: '4321' })).claims.name).toBe('Deepak')
  })
})
