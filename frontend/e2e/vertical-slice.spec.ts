// The demo vertical slice with three browser contexts (coordinator, customer, driver), each logging in
// manually, against the production build. Other tabs are NOT reloaded: they must update by themselves.
import { expect, test, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'

// Offline proof: every request that leaves 127.0.0.1 is blocked and recorded. The test fails if any happens.
const external: string[] = []

async function login(browser: Browser, username: string, mobile = false): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } })
  opened.push(ctx)
  await ctx.route('**/*', (route) => {
    const host = new URL(route.request().url()).hostname
    if (host === '127.0.0.1' || host === 'localhost') return route.continue()
    external.push(route.request().url())
    return route.abort()
  })
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  return page
}

test('customer -> driver -> coordinator -> disruption -> war room -> approve -> customer', async ({ browser, request }) => {
  // repeatable start: reset the seeded demo data
  const tok = (await (await request.post('/api/auth/login', { data: { username: 'coordinator', password: PASSWORD } })).json()).access_token
  expect((await request.post('/api/admin/reset', { headers: { Authorization: `Bearer ${tok}` } })).ok()).toBeTruthy()

  const coordinator = await login(browser, 'coordinator')
  const customer = await login(browser, 'customer_a')
  const driver = await login(browser, 'driver1', true)

  // 1 customer views the order: original promise visible, risk low
  await customer.getByRole('button', { name: /ORD-G1/ }).click()
  const detail = customer.getByTestId('order-detail')
  await expect(detail.getByText('Original promise', { exact: true })).toBeVisible()
  await expect(detail.getByText('Delay risk: Low')).toBeVisible()
  await customer.screenshot({ path: `${SHOTS}/01-customer-before.png`, fullPage: true })

  // 2 driver advances a milestone
  await expect(driver.getByText('SHP-G1')).toBeVisible()
  await driver.getByRole('button', { name: /Confirm: Loaded, waiting at plant gate/ }).click()
  await expect(driver.getByText('Milestone recorded.')).toBeVisible()
  await driver.screenshot({ path: `${SHOTS}/02-driver.png`, fullPage: true })

  // 3 the coordinator sees it WITHOUT a reload (live sync), on the table and the map
  const row = coordinator.locator('tr', { hasText: 'SHP-G1' })
  await expect(row.getByText('Loaded, waiting at plant gate')).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.locator('.leaflet-container')).toBeVisible()
  await expect(coordinator.getByText('Illustrative routes. Positions are simulated.')).toBeVisible()
  await expect(coordinator.getByText('SHP-G1 loaded and waiting at the plant gate')).toBeVisible()

  // 4 disruption injected -> ETA and risk change -> alert
  await coordinator.getByLabel('Disruption preset').selectOption('FLOOD_R1')
  await coordinator.getByRole('button', { name: 'Inject disruption' }).click()
  await expect(coordinator.getByText('Disruption injected. Predictions recalculated.')).toBeVisible()
  await expect(row.getByText('High')).toBeVisible()
  await expect(coordinator.getByText('Risk changed from LOW to HIGH: SHP-G1')).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/03-control-tower.png`, fullPage: true })
  await coordinator.getByRole('button', { name: /Open alerts/ }).click()
  const drawer = coordinator.getByRole('dialog', { name: 'Alerts' })
  const alert = drawer.locator('li', { hasText: 'Delay risk HIGH: SHP-G1' })
  await expect(alert.getByText(/REROUTE via North Bypass/)).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/04-alerts.png` })
  await alert.getByRole('button', { name: 'Shipment' }).click()

  // shipment detail: reason shown
  await expect(coordinator.getByText('Road closure wait')).toBeVisible()
  await expect(coordinator.getByText(/P50 moved \+\d/)).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/05-shipment-detail.png`, fullPage: true })

  // 5 war room compares three options and explains the recommendation
  await coordinator.getByRole('link', { name: 'Open War Room' }).click()
  await coordinator.getByRole('button', { name: 'Run scenarios' }).click()
  await expect(coordinator.getByText('RECOMMENDED: REROUTE')).toBeVisible()
  for (const name of ['Continue', 'Reroute', 'Split shipment']) {
    await expect(coordinator.getByRole('columnheader', { name: new RegExp(name) })).toBeVisible()
  }
  await expect(coordinator.getByText('holds in 16 of 16 stress cases')).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/06-war-room.png`, fullPage: true })

  // 6 coordinator approves; shipment updates
  await coordinator.getByRole('button', { name: 'Approve Reroute' }).click()
  await expect(coordinator.getByText(/Reroute approved and applied/)).toBeVisible()
  await expect(coordinator.getByText(/is APPLIED/)).toBeVisible()

  // 7 the customer sees the updated expected delivery beside the original promise, no reload
  await expect(detail.getByText('Original promise', { exact: true })).toBeVisible()
  await expect(detail.getByText('Updated expected delivery', { exact: true })).toBeVisible()
  await expect(detail.getByText(/rerouted to protect the delivery time/).first()).toBeVisible({ timeout: 10_000 })
  await expect(customer.getByText(/Rerouting has been initiated/)).toBeVisible()
  await expect(customer.getByText(/Rs \d/)).toHaveCount(0) // no internal costs
  await customer.screenshot({ path: `${SHOTS}/07-customer-after.png`, fullPage: true })

  // 8 the driver sees the route instruction, no reload
  await expect(driver.getByText(/follow North Bypass/)).toBeVisible({ timeout: 10_000 })

  // 9 analytics: O5 dashboard, Panel A modelled benefit and the audit trail
  await coordinator.getByRole('link', { name: 'Analytics' }).click()
  await expect(coordinator.getByText('On-time performance by route')).toBeVisible()
  await expect(coordinator.getByText('Delay causes by transporter company (attributed hours)')).toBeVisible()
  await expect(coordinator.getByText('Delay causes: totals')).toBeVisible()
  await expect(coordinator.locator('.recharts-bar-rectangle').first()).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/08-analytics.png`, fullPage: true })
  await coordinator.getByRole('tab', { name: 'Business impact' }).click()
  await expect(coordinator.getByText(/MODELLED - ILLUSTRATIVE SCENARIO/)).toBeVisible()
  await expect(coordinator.locator('tr', { hasText: 'SHP-G1' }).getByText('REROUTE')).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/09-business-impact.png`, fullPage: true })
  await coordinator.getByRole('tab', { name: 'Audit trail' }).click()
  await expect(coordinator.getByText('INTERVENTION_APPROVED')).toBeVisible()

  // a customer cannot open coordinator pages
  await customer.goto('/tower')
  await expect(customer).toHaveURL(/\/customer$/)

  // the whole demo ran without a single request to the internet
  expect(external).toEqual([])
})
