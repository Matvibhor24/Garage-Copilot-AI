import { expect, test } from '@playwright/test'

// Owner > Floor: the 3D garage shows every open job at its station, and the crew list opens a job.
test('owner floor shows the garage live and inspects a job', async ({ page }, info) => {
  await page.goto('/owner')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByRole('button', { name: /Continue as Asha/ }).click()
  await page.getByRole('link', { name: 'Floor' }).click()

  await expect(page.getByText('[FLOOR]')).toBeVisible()
  await expect(page.locator('.gf-stage canvas')).toBeVisible()
  const flow = page.locator('.gf-numbers')
  await expect(flow).toContainText('1At door')
  await expect(flow).toContainText('2In bays')
  await expect(flow).toContainText('1Ready')

  await page.locator('.gf-crew button', { hasText: 'Raju' }).click()
  await expect(page.locator('.gf-inspector')).toContainText('J-1041')
  await expect(page.locator('.gf-inspector')).toContainText('Pulsar 150')
  await page.getByRole('button', { name: 'Open in 3D' }).click()
  await expect(page.getByRole('dialog')).toContainText('Pulsar 150')
  await page.getByRole('dialog').getByRole('button', { name: 'Close' }).click()

  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
  await info.attach('floor', { body: await page.screenshot(), contentType: 'image/png' })
})
