import { expect, test } from '@playwright/test'

// C07: browser history must never bring back a signed-in mechanic screen. Only a reload keeps the shift.
async function signIn(page) {
  await page.goto('/')
  await page.getByRole('link', { name: /Mechanic: Open the mechanic screen/ }).click()
  await page.getByLabel('Your name').fill('Raju')
  for (const d of '1234') await page.getByRole('button', { name: d, exact: true }).click()
  await expect(page.getByRole('button', { name: 'Start shift' })).toBeVisible()
}
const pinScreen = (page) => expect(page.getByRole('heading', { name: "Who's working?" })).toBeVisible()

test('Back then Forward asks for the PIN again', async ({ page }) => {
  await signIn(page)
  await page.goBack()
  await expect(page.getByRole('heading', { name: /The AI co-worker for India's garages/ })).toBeVisible()
  await page.goForward()
  await pinScreen(page)
  await expect(page.getByRole('button', { name: 'Start shift' })).toHaveCount(0)
})

test('after Sign out, Back and Forward never show the voice screen', async ({ page }) => {
  await signIn(page)
  await page.getByRole('button', { name: 'Menu' }).click()
  await page.getByRole('menuitem', { name: 'Sign out' }).click()
  await pinScreen(page)
  await page.goBack()
  await page.goForward()
  await pinScreen(page)
  await page.goBack()
  await page.goBack().catch(() => {})
  await page.goForward()
  await page.goForward()
  await pinScreen(page)
})

test('leaving for another page and coming back with Back asks for the PIN', async ({ page }) => {
  await signIn(page)
  await page.goto('/owner') // a full page load, like typing another address
  await page.goBack()
  await pinScreen(page)
})

test('a reload keeps the shift', async ({ page }) => {
  await signIn(page)
  await page.reload()
  await expect(page.getByRole('button', { name: 'Start shift' })).toBeVisible()
})
