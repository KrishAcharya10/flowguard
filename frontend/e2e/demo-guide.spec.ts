// The in-app Demo guide: one-click setup, presenter panel, and use case 4 (Split) end to end.
import { expect, test, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })


const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'

async function login(browser: Browser, username: string): Promise<Page> {
  const ctx = await browser.newContext()
  opened.push(ctx)
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  return page
}

test('demo guide: use case 4 (split) via "Jump to the decision point"', async ({ browser }) => {
  const co = await login(browser, 'coordinator')
  await co.getByRole('link', { name: 'Demo guide' }).click()
  await expect(co.getByRole('heading', { name: 'Demo guide' })).toBeVisible()
  await expect(co.getByRole('list', { name: 'Use cases' }).getByRole('listitem')).toHaveCount(8)
  await co.screenshot({ path: `${SHOTS}/10-demo-guide.png`, fullPage: true })

  await co.getByRole('list', { name: 'Use cases' }).getByRole('listitem').filter({ hasText: 'Truck late at the plant' }).click()
  await co.getByRole('button', { name: /Jump to the decision point/ }).click()
  await expect(co.getByText(/Use case 4 ready at the decision point/)).toBeVisible()
  const panel = co.getByRole('complementary', { name: 'Presenter guide' })
  await expect(panel).toBeVisible()
  await expect(panel.getByText('NEXT:')).toBeVisible()
  await co.screenshot({ path: `${SHOTS}/11-demo-guide-active.png`, fullPage: true })

  // the panel's "Go" button takes the presenter to the next coordinator step (the War Room)
  await panel.getByRole('button', { name: 'Go' }).click()   // next step: Open SHP-BHW-1116-03 → War Room
  await expect(co).toHaveURL(/\/shipments\/SHP-BHW-1116-03\/war-room$/)
  await panel.getByRole('button', { name: 'Minimise presenter guide' }).click()
  await co.getByRole('button', { name: 'Run scenarios' }).click()
  await expect(co.getByText('RECOMMENDED: SPLIT')).toBeVisible()
  await expect(co.getByText('No alternative route is defined for this route')).toBeVisible()
  await co.screenshot({ path: `${SHOTS}/12-war-room-split.png`, fullPage: true })
  await co.getByRole('button', { name: 'Approve Split shipment' }).click()
  await expect(co.getByText(/Split shipment approved and applied/)).toBeVisible()

  await co.goto('/shipments/SHP-BHW-1116-03')
  await expect(co.getByText(/This shipment was split/)).toBeVisible()
  await expect(co.getByRole('link', { name: 'SHP-BHW-1116-03-U' })).toBeVisible()

  const relief = await login(browser, 'relief_tr1')
  await expect(relief.getByText('SHP-BHW-1116-03-U')).toBeVisible()
  const cust = await login(browser, 'customer_c')
  await cust.getByRole('button', { name: /ORD-BHW-1116-03/ }).click()
  const order = cust.getByTestId('order-detail')
  await expect(order.getByText(/SHP-BHW-1116-03-U · urgent delivery, 6 t/)).toBeVisible()
  await expect(order.getByText(/SHP-BHW-1116-03-R · remainder delivery, 14 t/)).toBeVisible()
  await cust.screenshot({ path: `${SHOTS}/13-customer-split.png`, fullPage: true })
})

test('demo guide "Start" + custom disruption duration in the Control Tower', async ({ browser }) => {
  const co = await login(browser, 'coordinator')
  await co.goto('/demo')
  await co.getByRole('list', { name: 'Use cases' }).getByRole('listitem').filter({ hasText: 'Truck late at the plant' }).click()
  await co.getByRole('button', { name: /Start from the beginning/ }).click()
  await expect(co.getByText(/Use case 4 ready: demo data reset/)).toBeVisible()
  await co.getByRole('complementary', { name: 'Presenter guide' }).getByRole('button', { name: 'Minimise presenter guide' }).click()
  await co.getByRole('link', { name: 'Control Tower', exact: true }).click()
  await co.getByLabel('Disruption preset').selectOption('LATE_DISPATCH')
  await co.getByLabel('Shipment', { exact: true }).selectOption('SHP-BHW-1116-03')
  await co.getByLabel('Custom duration').check()
  for (const label of ['Min h', 'Most likely h', 'Max h']) await co.getByLabel(label).fill('4')
  await co.getByRole('button', { name: 'Inject disruption' }).click()
  await expect(co.getByText('Disruption injected. Predictions recalculated.')).toBeVisible()
  await expect(co.locator('tr', { hasText: 'SHP-BHW-1116-03' }).getByText('High')).toBeVisible()
})
