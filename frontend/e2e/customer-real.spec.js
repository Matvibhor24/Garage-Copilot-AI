import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'

// The customer page in normal mode (no demo backend, polls every 4 s like local dev without Firebase), with /api
// answered by a stub that follows the real backend: same JSON (fixtures/customer-view.json is a real GET
// /api/j/{token} response), one decision per sent quote, a repeat returns the stored decision.
const VIEW = JSON.parse(readFileSync(new URL('./fixtures/customer-view.json', import.meta.url)))
const BASE = 'http://localhost:5182'
const TOKEN = `${Buffer.from(JSON.stringify({ g: 'shree-auto', j: 'J-1042', exp: 1792003795 })).toString('base64url')}.sig`

function fakeBackend({ applyDecision = true, staleUntilPost = false } = {}) {
  const state = { view: structuredClone(VIEW), posts: 0, decided: null }
  async function route(r) {
    const url = new URL(r.request().url())
    const m = url.pathname.match(/\/quotes\/([^/]+)\/(approve|reject)$/)
    if (!m) return r.fulfill({ json: staleUntilPost && !state.posts ? VIEW : state.view })
    state.posts += 1
    await new Promise((ok) => setTimeout(ok, 300))
    const q = state.view.quotes.find((x) => x.id === m[1])
    if (!state.decided) {
      state.decided = m[2] === 'approve' ? 'approved' : 'rejected'
      if (applyDecision) {
        Object.assign(q, { status: state.decided, by: 'customer' })
        if (state.decided === 'approved') state.view = { ...state.view, labour: q.labour, bill: state.view.bill + q.labour }
      }
    }
    return r.fulfill({ json: { quote_id: q.id, status: state.decided, total: q.total } })
  }
  return { state, route }
}

async function open(context, backend) {
  const page = await context.newPage()
  await page.route('**/api/**', backend.route)
  await page.goto(`${BASE}/j/${TOKEN}`)
  await expect(page.getByText('Extra work found')).toBeVisible()
  return page
}

test('approve: confirmation, then the card leaves and the quote shows as approved, also after a refresh', async ({ context }) => {
  const backend = fakeBackend()
  const page = await open(context, backend)
  await page.getByRole('button', { name: 'Approve ₹950' }).click()
  await expect(page.getByRole('heading', { name: 'Approved' })).toBeVisible()
  await expect(page.getByText('Extra work found')).toHaveCount(0)
  await expect(page.locator('.quote-done')).toHaveCount(0)
  await expect(page.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  await page.reload()
  await expect(page.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  await expect(page.getByText('Extra work found')).toHaveCount(0)
})

test('decline also leaves the decided list showing Declined', async ({ context }) => {
  const backend = fakeBackend()
  const page = await open(context, backend)
  await page.getByRole('button', { name: 'Decline' }).click()
  await page.getByRole('button', { name: 'Yes, decline' }).click()
  await expect(page.getByRole('heading', { name: 'Declined' })).toBeVisible()
  await expect(page.locator('.chip-bad', { hasText: 'Declined' })).toBeVisible()
  await expect(page.locator('.quote, .quote-done')).toHaveCount(0)
})

test('a double tap sends one request and shows no error', async ({ context }) => {
  const backend = fakeBackend()
  const page = await open(context, backend)
  await page.getByRole('button', { name: 'Approve ₹950' }).dblclick()
  await expect(page.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  expect(backend.state.posts).toBe(1)
  await expect(page.locator('.toast')).toHaveCount(0)
})

test('a second customer tab catches up on its own', async ({ context }) => {
  const backend = fakeBackend()
  const a = await open(context, backend)
  const b = await open(context, backend)
  await a.getByRole('button', { name: 'Approve ₹950' }).click()
  await expect(a.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  await expect(b.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  await expect(b.getByText('Extra work found')).toHaveCount(0)
})

test('a late tap in a stale tab shows the decision that stands, without an error', async ({ context }) => {
  const backend = fakeBackend({ staleUntilPost: true }) // this tab keeps seeing "pending" until it taps
  const b = await open(context, backend)
  backend.state.decided = 'approved' // decided in another tab
  Object.assign(backend.state.view.quotes[0], { status: 'approved' })
  await b.getByRole('button', { name: 'Decline' }).click()
  await b.getByRole('button', { name: 'Yes, decline' }).click()
  // The brief "Approved" confirmation (1.6 s) is checked in the approve test; under full-suite load (software
  // WebGL on every page) it can come and go between checks, so here only the outcome is checked.
  await expect(b.locator('.chip-ok', { hasText: 'Approved' })).toBeVisible()
  await expect(b.locator('.chip-bad')).toHaveCount(0)
  await expect(b.locator('.quote')).toHaveCount(0)
  await expect(b.locator('.toast')).toHaveCount(0)
  expect(backend.state.posts).toBe(1)
})

test('if the server still says pending, the buttons come back instead of a stuck "Approved"', async ({ context }) => {
  // What the old backend did after a re-seed: answered "approved" without saving it.
  const backend = fakeBackend({ applyDecision: false })
  const page = await open(context, backend)
  await page.getByRole('button', { name: 'Approve ₹950' }).click()
  await expect(page.getByRole('heading', { name: 'Approved' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Approve ₹950' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Approved' })).toHaveCount(0)
})
