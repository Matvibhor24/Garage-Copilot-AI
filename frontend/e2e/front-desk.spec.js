import { expect, test } from '@playwright/test'

// C15: a customer calls the garage from their status page; the owner sees the call, confirms the estimate and
// closes the callback.
test('customer calls the garage; the owner handles the estimate and the callback', async ({ page, context }) => {
  await page.goto('/mechanic')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByLabel('Your name').fill('Raju')
  for (const d of '1234') await page.getByRole('button', { name: d, exact: true }).click()
  await page.getByRole('button', { name: 'Start shift' }).click()
  const orb = page.locator('.orb')
  for (let i = 0; i < 2; i++) { // intake, service
    await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
    await orb.dispatchEvent('pointerdown')
    await orb.dispatchEvent('pointerup')
    await expect(page.locator('.orb-thinking, .orb-speaking')).toBeVisible()
  }
  await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })

  const customer = await context.newPage()
  await customer.goto('/j/demo-J-1042')
  await customer.getByRole('button', { name: 'Call the garage' }).click()
  const call = customer.getByRole('dialog', { name: /Call Shree Auto/ })
  await expect(call).toBeVisible()
  const talk = async () => {
    await expect(call.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
    await call.locator('.orb').dispatchEvent('pointerdown')
    await call.locator('.orb').dispatchEvent('pointerup')
    await expect(call.locator('.orb-thinking, .orb-speaking')).toBeVisible()
    await expect(call.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
  }
  await talk()
  await expect(call.locator('.bubble-agent').last()).toContainText('Your Splendor Plus is in service right now.', { timeout: 20_000 })
  await talk()
  await expect(call.locator('.tool-chip').last()).toContainText('Wait ·', { timeout: 20_000 })
  await talk()
  await expect(call.locator('.tool-chip').last()).toContainText('Status link sent to the number on file', { timeout: 20_000 })
  await talk()
  await expect(call.locator('.tool-chip').last()).toContainText('owner will confirm', { timeout: 20_000 })
  await talk()
  await expect(call.locator('.tool-chip').last()).toContainText('Callback requested', { timeout: 20_000 })
  await expect(call.locator('.bubble-mechanic')).toHaveCount(5) // one call all along, not restarted
  expect(await customer.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
  await call.getByRole('button', { name: 'End call' }).click()
  await expect(call).toHaveCount(0)

  const owner = await context.newPage()
  await owner.goto('/owner')
  await owner.getByRole('button', { name: /Continue as Asha/ }).click()
  const card = owner.getByLabel('Calls')
  await expect(card).toContainText('Hello, is my Splendor ready?')
  await expect(card).toContainText('their own link')
  await card.getByRole('button', { name: 'Send ₹1,170' }).click()
  await expect(owner.getByText('Estimate sent to Ramesh')).toBeVisible()
  await expect(card).toContainText('About the bill')
  await card.getByRole('button', { name: 'Done' }).click()
  await expect(card).not.toContainText('About the bill')
  expect(await owner.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
})
