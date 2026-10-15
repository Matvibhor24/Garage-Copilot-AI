import { expect, test } from '@playwright/test'

// C09: the owner sees and changes the auto-approve limit; bad values are refused; the feed says what changed.
test('owner changes the auto-approve limit in Settings', async ({ page }) => {
  await page.goto('/owner')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByRole('button', { name: /Continue as Asha/ }).click()
  await page.getByRole('link', { name: 'Settings' }).click()
  const limit = page.getByLabel('Auto-approve limit (₹)')
  await expect(limit).toHaveValue('500')
  await expect(page.getByText('Quotes up to this amount are approved without asking the customer. 0 = always ask the customer.')).toBeVisible()

  await limit.fill('200000')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('auto-approve limit must be between 0 and 1,00,000')).toBeVisible()

  await limit.fill('0')
  await page.getByRole('button', { name: 'Save' }).click()
  await expect(page.getByText('Changed the auto-approve limit from ₹500 to ₹0')).toBeVisible()
  await expect(page.getByText('Auto-approve now: always ask the customer')).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

  await page.getByRole('link', { name: 'Today' }).click()
  await expect(page.locator('.feed')).toContainText('changed settings')
  await expect(page.locator('.feed')).toContainText('the auto-approve limit from ₹500 to ₹0')
})
