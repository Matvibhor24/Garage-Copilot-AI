import { expect, test } from '@playwright/test'

// C13: consumables in the Stock tab; bill split, cost and margin in the job viewer.
test("owner sees consumables in stock and a job's cost and margin", async ({ page }) => {
  await page.goto('/owner')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByRole('button', { name: /Continue as Asha/ }).click()
  await expect(page.locator('.tile').filter({ hasText: 'Revenue today' })).toContainText('margin')

  await page.locator('.job-card', { hasText: 'J-1036' }).click()
  const viewer = page.locator('dialog.v3d-dialog')
  await expect(viewer.getByLabel('Bill and margin')).toContainText('Consumables')
  await expect(viewer.getByLabel('Bill and margin')).toContainText('₹1,850')
  await expect(viewer.getByLabel('Bill and margin')).toContainText('Margin')
  await viewer.getByRole('button', { name: 'Close' }).click()

  await page.getByRole('link', { name: 'Stock' }).click()
  await page.getByRole('button', { name: 'Consumables' }).click()
  await expect(page.locator('.part', { hasText: 'M6 bolt' })).toContainText('Consumable · garage cost')
  await expect(page.locator('.part', { hasText: 'Brake cleaner' })).toContainText('Consumable · billed')
  await expect(page.locator('.part', { hasText: 'Clutch plate set' })).toHaveCount(0)
  await page.getByRole('button', { name: 'Parts' }).click()
  await expect(page.locator('.part', { hasText: 'Clutch plate set' }).first()).toContainText('fitted with 4 consumables')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
})
