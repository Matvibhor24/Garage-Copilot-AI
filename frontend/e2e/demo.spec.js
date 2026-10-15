import { expect, test } from '@playwright/test'

// No screen may scroll sideways, at any size.
async function noSideScroll(page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0)
}

// The demo job from diagrams/job-workflow.png, across the three screens, in demo mode.
test('mechanic, customer and owner screens run the demo job', async ({ page, context }, info) => {
  await page.goto('/')
  await page.evaluate(() => localStorage.clear())
  await page.reload()
  await expect(page.getByRole('heading', { name: /The AI co-worker for India's garages/ })).toBeVisible()
  await noSideScroll(page)
  await info.attach('home', { body: await page.screenshot(), contentType: 'image/png' })

  // Mechanic signs in with name + PIN
  await page.getByRole('link', { name: /Mechanic: Open the mechanic screen/ }).click()
  await page.getByLabel('Your name').fill('Raju')
  for (const d of '0000') await page.getByRole('button', { name: d, exact: true }).click()
  await expect(page.getByText('Wrong name or PIN')).toBeVisible()
  for (const d of '1234') await page.getByRole('button', { name: d, exact: true }).click()
  await page.getByRole('button', { name: 'Start shift' }).click()

  const orb = page.locator('.orb')
  async function talk() {
    await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
    await orb.dispatchEvent('pointerdown')
    await orb.dispatchEvent('pointerup')
    await expect(page.locator('.orb-thinking, .orb-speaking')).toBeVisible()
    await expect(page.locator('.orb-idle')).toBeVisible({ timeout: 20_000 })
  }
  for (let i = 0; i < 4; i++) await talk() // intake, service, stock check, quote
  await expect(page.locator('.job-strip')).toContainText('Waiting on customer')
  await noSideScroll(page)
  await info.attach('mechanic', { body: await page.screenshot(), contentType: 'image/png' })

  // Customer approves on their link (another tab)
  const customer = await context.newPage()
  await customer.goto('/j/demo-J-1042')
  await expect(customer.getByText('Extra work found')).toBeVisible()
  await expect(customer.locator('.tl-now')).toContainText('In service')
  await customer.getByRole('button', { name: 'Approve ₹950' }).click()
  await expect(customer.getByRole('heading', { name: 'Approved' })).toBeVisible()

  // Mechanic hears it
  await expect(page.locator('.bubble-notice')).toContainText('Ramesh approved. Go ahead.', { timeout: 10_000 })
  await talk() // used one clutch plate
  await talk() // washing, after the repair (C10)
  await expect(customer.locator('.tl-now')).toContainText('Washing')
  await talk() // job done
  await expect(page.locator('.job-strip')).toContainText('Closed')
  await talk() // manual lookup (made-up demo answer)
  await expect(page.locator('.tool-chip').last()).toContainText('Manual · Demo manual p.12')
  await expect(page.locator('.bubble-agent').last()).toContainText('Demo answer, not a real spec')
  await talk() // not in the manual: the agent asks before searching online (C14)
  await expect(page.locator('.tool-chip').last()).toContainText('Not in the manual')
  await expect(page.locator('.bubble-agent').last()).toContainText('Shall I search online for known causes and fixes?')
  await talk() // "Yes, search online."
  await expect(page.locator('.tool-chip').last()).toContainText('Web · demo-site-one.example, demo-site-two.example')
  await expect(page.locator('.bubble-agent').last()).toContainText('From the web, not the manual')

  await expect(customer.getByRole('heading', { name: 'Ready for pickup' })).toBeVisible({ timeout: 10_000 })
  await expect(customer.locator('.bill-final')).toContainText('₹950')
  await noSideScroll(customer)
  await info.attach('customer', { body: await customer.screenshot({ fullPage: true }), contentType: 'image/png' })

  // Owner sees the day and answers the agent's reorder ask
  const owner = await context.newPage()
  await owner.goto('/owner')
  await owner.getByRole('button', { name: /Continue as Asha/ }).click()
  await expect(owner.locator('.tile').filter({ hasText: 'Revenue today' })).toContainText('₹12,400')
  await expect(owner.locator('.tile').filter({ hasText: 'Open jobs' })).toContainText('5') // + the two F12 floor fillers
  await expect(owner.locator('.agent-ask')).toContainText('Clutch plate set down to 1. Reorder 5 from Sai Spares?')
  await owner.getByRole('button', { name: 'Yes, reorder' }).click()
  await expect(owner.getByText('Ordered 5 from Sai Spares')).toBeVisible()
  await expect(owner.locator('.agent-ask')).toHaveCount(0)
  await owner.getByText('Messages', { exact: true }).click()
  await expect(owner.locator('.feed')).toContainText('Sai Spares')

  // Owner asks the voice agent about the day (demo script answers from the same data)
  await owner.getByRole('button', { name: 'Ask GarageCopilot' }).click()
  const panel = owner.locator('.owner-voice')
  await expect(panel.locator('.orb-idle')).toBeVisible()
  await panel.locator('.orb').dispatchEvent('pointerdown')
  await panel.locator('.orb').dispatchEvent('pointerup')
  await expect(panel.locator('.bubble-agent').last()).toContainText('5 open jobs')
  await expect(panel.locator('.orb-idle')).toBeVisible()
  await panel.getByRole('button', { name: /Ask: “What's pending approval/ }).click()
  await expect(panel.locator('.bubble-agent').last()).toContainText('Nothing is waiting')
  // The 3D job viewer still opens on top of the panel
  await owner.locator('.job-card').first().click()
  await expect(owner.locator('dialog.v3d-dialog')).toBeVisible()
  await owner.locator('dialog.v3d-dialog').getByRole('button', { name: 'Close' }).click()
  await expect(owner.locator('dialog.v3d-dialog')).toHaveCount(0)
  await expect(panel).toBeVisible()
  await noSideScroll(owner)
  await info.attach('owner', { body: await owner.screenshot({ fullPage: true }), contentType: 'image/png' })
})

test('a bad customer link explains itself', async ({ page }) => {
  await page.goto('/j/not-a-real-token')
  await expect(page.getByRole('heading', { name: 'Link not working' })).toBeVisible()
})
