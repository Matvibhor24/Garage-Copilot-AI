import { expect, test } from '@playwright/test'

// C16: the landing page explains the product, then each Try-it card opens the screen it describes.
const noSideScroll = async (page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

test('landing page renders every section without sideways scroll', async ({ page }, info) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: "The AI co-worker for India's garages" })).toBeVisible()
  await expect(page.getByText('Mechanics talk, it does the paperwork, customers approve from their phone.')).toBeVisible()
  await expect(page.getByRole('img', { name: /The mechanic speaks, a job card appears/ })).toBeVisible()
  for (const h of ['The problem', 'How it works', 'What makes it different', 'Try it']) {
    await expect(page.getByRole('heading', { name: h, exact: true })).toBeVisible()
  }
  const wide = page.viewportSize().width >= 640 // phones get a stacked version of the diagram
  await expect(wide ? page.getByRole('img', { name: 'How GarageCopilot works' }) : page.locator('.lp-flow-v')).toBeVisible()
  await expect(page.getByText('Built on Gemini · ADK · Cloud Run · Firestore')).toBeVisible()
  await noSideScroll(page)
  await info.attach('landing', { body: await page.screenshot({ fullPage: true }), contentType: 'image/png' })
})

test('each Try-it card opens the screen it promises', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: /Mechanic: Open the mechanic screen/ }).click()
  await expect(page.getByLabel('Your name')).toBeVisible() // "Sign in as Raju, PIN 1234"
  await page.goto('/')
  await page.getByRole('link', { name: /Owner: Open the owner dashboard/ }).click()
  await expect(page.getByRole('button', { name: /Continue as Asha/ })).toBeVisible()
  await page.goto('/')
  await page.getByRole('link', { name: /Customer: Open Ramesh's page/ }).click()
  await expect(page).toHaveURL(/\/j\/demo-J-1042$/)
})

test('call the garage from the landing page (front desk, number not verified)', async ({ page }) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByRole('button', { name: 'Call the garage' }).click()
  const call = page.getByRole('dialog', { name: /Call Shree Auto/ })
  await expect(call.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
  await call.locator('.orb').dispatchEvent('pointerdown')
  await call.locator('.orb').dispatchEvent('pointerup')
  await expect(call.locator('.bubble-agent').last()).toContainText("can't share job details", { timeout: 20_000 })
  await noSideScroll(page)
})

test('reduced motion shows the whole flow at once', async ({ browser }) => {
  const context = await browser.newContext({ reducedMotion: 'reduce' })
  const page = await context.newPage()
  await page.goto('http://localhost:5180/')
  await expect(page.locator('.flow-step.on')).toHaveCount(4)
  await context.close()
})
