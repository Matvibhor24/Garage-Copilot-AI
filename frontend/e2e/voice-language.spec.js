import { expect, test } from '@playwright/test'

// C11: the reply-language picker on the mechanic and owner voice screens, remembered on this device.
test('mechanic and owner can pin the reply language', async ({ page }) => {
  await page.goto('/mechanic')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await page.getByLabel('Your name').fill('Raju')
  for (const d of '1234') await page.getByRole('button', { name: d, exact: true }).click()
  await page.getByRole('button', { name: 'Start shift' }).click()
  const picker = page.getByLabel('Reply language')
  await expect(picker).toHaveValue('auto')
  await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
  await picker.selectOption('hi')
  await expect(page.getByText('Replies pinned to that language')).toBeVisible()
  await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 }) // a fresh session started by itself
  await expect(page.locator('.note').last()).toContainText('replies stay in the language you picked')
  expect(await page.evaluate(() => localStorage.getItem('gc.lang.mechanic'))).toBe('hi')
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)

  await page.goto('/owner')
  await page.getByRole('button', { name: /Continue as Asha/ }).click()
  await page.getByRole('button', { name: 'Ask GarageCopilot' }).click()
  const ownerPicker = page.locator('.owner-voice').getByLabel('Reply language')
  await expect(ownerPicker).toHaveValue('auto') // per screen
  await ownerPicker.selectOption('mr')
  await page.reload()
  await page.getByRole('button', { name: /Continue as Asha/ }).click() // a reload signs the demo owner out
  await page.getByRole('button', { name: 'Ask GarageCopilot' }).click()
  await expect(page.locator('.owner-voice').getByLabel('Reply language')).toHaveValue('mr')
})
