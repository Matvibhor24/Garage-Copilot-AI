import { expect, test } from '@playwright/test'

// C17: the owner's records tabs, on a phone and a laptop.
const noSideScroll = async (page) =>
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

async function owner(page) {
  await page.goto('/owner')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByRole('button', { name: /Continue as Asha/ }).click()
  await expect(page.locator('.tile').first()).toBeVisible()
}

test('tabs in order, Today first', async ({ page }) => {
  await owner(page)
  await expect(page.getByRole('navigation', { name: 'Owner sections' }).getByRole('link')).toHaveText(
    ['Today', 'Floor', 'Jobs', 'Customers', 'Vehicles', 'Staff', 'Stock', 'Settings'])
  await noSideScroll(page)
})

test("Jobs: totals, filters, a job's detail and CSV export", async ({ page }) => {
  await owner(page)
  await page.getByRole('link', { name: 'Jobs', exact: true }).click()
  const jobs = page.getByLabel('Jobs', { exact: true })
  await page.getByRole('group', { name: 'Dates' }).getByRole('button', { name: 'All' }).click()
  await expect(jobs.getByLabel('Totals for this filter')).toContainText('Revenue')
  await expect(jobs.locator('tbody tr').first()).toBeVisible()
  await page.getByRole('group', { name: 'Status' }).getByRole('button', { name: 'Open' }).click()
  await expect(jobs.locator('tbody tr').first()).toContainText('J-10')
  await expect(jobs.locator('.chip-ok', { hasText: 'Closed' })).toHaveCount(0)
  await page.getByRole('group', { name: 'Status' }).getByRole('button', { name: 'All' }).click()
  await page.getByLabel('Search plate, customer or job').fill('MH14GH7710')
  await expect(jobs.locator('tbody tr').first()).toContainText('Vikas')
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Export CSV' }).click()
  expect((await download).suggestedFilename()).toMatch(/^garage-jobs.*\.csv$/)
  await jobs.locator('tbody tr', { hasText: 'J-1038' }).click()
  const detail = page.locator('dialog.rec-dialog')
  await expect(detail).toContainText('Timeline')
  await expect(detail.getByLabel('Bill and margin')).toContainText('₹6,600')
  await noSideScroll(page)
  await detail.getByRole('button', { name: 'Close' }).click()
})

test('Customers and Vehicles open their history', async ({ page }) => {
  await owner(page)
  await page.getByRole('link', { name: 'Customers' }).click()
  await page.getByLabel('Search name, phone or plate').fill('vikas')
  const customers = page.getByLabel('Customers', { exact: true })
  await expect(customers.locator('tbody tr')).toHaveCount(1)
  await customers.locator('tbody tr', { hasText: 'Vikas' }).click()
  await expect(page.locator('dialog.rec-dialog')).toContainText('Total spent')
  await page.locator('dialog.rec-dialog').getByRole('button', { name: 'Close' }).first().click()
  await page.getByLabel('Search name, phone or plate').fill('Kiran')
  await customers.locator('tbody tr', { hasText: 'Kiran' }).click()
  await page.locator('dialog.rec-dialog').getByRole('button', { name: 'Send status link' }).click()
  await expect(page.getByText('Status link sent to Kiran')).toBeVisible()
  await page.locator('dialog.rec-dialog').getByRole('button', { name: 'Close' }).first().click()
  await noSideScroll(page)

  await page.getByRole('link', { name: 'Vehicles' }).click()
  const vehicles = page.getByLabel('Vehicles', { exact: true })
  await vehicles.locator('tbody tr', { hasText: 'MH 14 GH 7710' }).click()
  await expect(page.locator('dialog.rec-dialog')).toContainText('J-1038')
  await noSideScroll(page)
})

test('Staff: per-mechanic numbers and chart, add and switch off', async ({ page }) => {
  await owner(page)
  await page.getByRole('link', { name: 'Staff' }).click()
  await expect(page.getByRole('heading', { name: '2 mechanics' })).toBeVisible()
  const raju = page.getByRole('article', { name: 'Raju' })
  await expect(raju).toContainText('Finished today')
  await expect(raju.getByRole('figure')).toHaveAttribute('aria-label', /Raju: jobs finished per day/)
  await page.getByRole('group', { name: 'Period' }).getByRole('button', { name: 'This month' }).click()
  await expect(raju.locator('.bar-slot').first()).toBeVisible()
  await page.getByLabel('Name', { exact: true }).fill('Deepak')
  await page.getByLabel('PIN').fill('4321')
  await page.getByRole('button', { name: 'Add', exact: true }).click()
  await expect(page.getByRole('heading', { name: '3 mechanics' })).toBeVisible()
  page.once('dialog', (d) => d.accept())
  await raju.getByRole('button', { name: 'Switch off' }).click()
  await expect(raju).toContainText('Switched off')
  await expect(page.getByRole('heading', { name: '2 mechanics' })).toBeVisible()
  await noSideScroll(page)
})
