import { expect, test } from '@playwright/test'

// C12: the customer page is English by default, switches to Hindi, and remembers it on this device.
test('customer page: English by default, Hindi switch remembered', async ({ page }) => {
  await page.goto('/mechanic')
  await page.evaluate(() => localStorage.clear())
  // Open a job in the demo so the customer has a page and a message
  await page.getByLabel('Your name').fill('Raju')
  for (const d of '1234') await page.getByRole('button', { name: d, exact: true }).click()
  await page.getByRole('button', { name: 'Start shift' }).click()
  await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
  await page.locator('.orb').dispatchEvent('pointerdown')
  await page.locator('.orb').dispatchEvent('pointerup')
  await expect(page.locator('.tool-chip').first()).toContainText('Job J-1042 opened', { timeout: 20_000 })

  await page.goto('/j/demo-J-1042')
  await expect(page.getByRole('heading', { name: 'Checked in' }).first()).toBeVisible()
  await expect(page.getByRole('button', { name: 'English' })).toHaveAttribute('aria-pressed', 'true')
  await expect(page.locator('.cust-messages')).toContainText('Hi Ramesh, your Splendor Plus is checked in')
  await expect(page.getByText('Progress')).toBeVisible()

  await page.getByRole('button', { name: 'हिंदी' }).click()
  await expect(page.getByText('प्रगति')).toBeVisible()
  await expect(page.locator('.status-title')).toHaveText('गाड़ी जमा हुई')
  await expect(page.locator('.cust-messages')).toContainText('आपकी Splendor Plus')
  await expect(page.getByText('Progress')).toHaveCount(0)
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

  await page.reload()
  await expect(page.getByText('प्रगति')).toBeVisible()
  await page.getByRole('button', { name: 'English' }).click()
  await expect(page.getByText('Progress')).toBeVisible()
})
