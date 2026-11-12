// Live operations: the complete cross-role workflow on persistent backend records, in three separate browser
// contexts. No page is reloaded after login: every screen must update by itself (live sync).
//   order created -> assigned -> driver loads -> departs -> disruption -> alert -> War Room -> approve ->
//   customer notified -> simulation runs -> position events -> arrival -> proof of delivery -> history.
import { expect, test, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'
const external: string[] = []

async function login(browser: Browser, username: string, mobile = false): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } })
  opened.push(ctx)
  await ctx.route('**/*', (route) => {
    const host = new URL(route.request().url()).hostname
    if (host === '127.0.0.1' || host === 'localhost') return route.continue()
    // The only external call the app may make is for optional OpenStreetMap map tiles. Blocking them here also proves the
    // whole workflow still works offline (the map falls back to the local logistics network).
    if (host === 'tile.openstreetmap.org') return route.abort()
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

async function token(request: import('@playwright/test').APIRequestContext, user = 'coordinator') {
  return (await (await request.post('/api/auth/login', { data: { username: user, password: PASSWORD } })).json()).access_token as string
}

test.describe.configure({ mode: 'serial' })

test('full workflow across coordinator, driver and customer, then a live simulation run to delivery', async ({ browser, request }) => {
  test.setTimeout(300_000)
  const tok = await token(request)
  const auth = { Authorization: `Bearer ${tok}` }
  expect((await request.post('/api/admin/reset', { headers: auth })).ok()).toBeTruthy()

  const coordinator = await login(browser, 'coordinator')
  const customer = await login(browser, 'customer_b')

  // ---- 1. an order is created and assigned to a transporter, a free driver and a vehicle ----
  await coordinator.getByRole('button', { name: 'New order' }).click()
  const dialog = coordinator.getByRole('dialog', { name: 'Create order' })
  await dialog.getByLabel('Destination (route)').selectOption('R2')
  await dialog.getByLabel('Transporter').selectOption('TR-1')
  await dialog.getByLabel('Product').selectOption('FILM-L30')
  await dialog.getByLabel('Priority').selectOption('HIGH')
  await dialog.getByRole('button', { name: 'Create and assign' }).click()
  await expect(dialog.getByText(/created and assigned to Dilip Wagh/)).toBeVisible()
  const ids = (await dialog.locator('dd', { hasText: /^ORD-[A-Z]{3}-\d{4}-\d{2} \/ SHP-[A-Z]{3}-\d{4}-\d{2}$/ }).innerText()).split(' / ')
  const [orderId, shipmentId] = ids
  await expect(dialog.getByText('driver15', { exact: false }).first()).toBeVisible()
  await dialog.getByRole('button', { name: 'Close', exact: true }).click()

  // the customer who owns the destination sees the new order without reloading
  await expect(customer.getByRole('button', { name: new RegExp(orderId) })).toBeVisible({ timeout: 10_000 })
  await customer.getByRole('button', { name: new RegExp(orderId) }).click()

  // ---- 2. the driver logs in and sees the assigned shipment ----
  const driver = await login(browser, 'driver15', true)
  const card = driver.getByTestId(`driver-card-${shipmentId}`)
  await expect(card).toBeVisible()
  await expect(card.getByText('Planned', { exact: true }).first()).toBeVisible()

  // ---- 3. the driver starts loading; coordinator and customer update by themselves ----
  await card.getByRole('button', { name: 'Confirm: Loading at Plant X' }).click()
  await expect(driver.getByText('Milestone recorded.')).toBeVisible()
  const row = coordinator.locator('tr', { hasText: shipmentId })
  await expect(row.getByText('Loading at Plant X')).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByText(`Driver started loading ${shipmentId}`)).toBeVisible()
  await expect(customer.getByText('Loading started at Plant X')).toBeVisible({ timeout: 10_000 })

  // ---- 4. the driver marks the shipment in transit; it appears on the control tower map ----
  await card.getByRole('button', { name: 'Confirm: Loaded, waiting at plant gate' }).click()
  await expect(driver.getByText('Milestone recorded.')).toBeVisible()
  await card.getByRole('button', { name: 'Confirm: In transit' }).click()
  await expect(row.getByText('In transit')).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByText(`${shipmentId} departed Plant X`)).toBeVisible()
  await expect(customer.getByText('Left Plant X, on its way to you')).toBeVisible({ timeout: 10_000 })
  const map = await (await request.get('/api/control-tower/map-data', { headers: auth })).json()
  expect(map.vehicles.some((v: { shipment_id: string }) => v.shipment_id === shipmentId)).toBeTruthy()
  await driver.screenshot({ path: `${SHOTS}/22-driver-app.png`, fullPage: true })

  // ---- 5. a disruption occurs; the engine recalculates; the coordinator gets an alert ----
  await coordinator.getByLabel('Disruption preset').selectOption('FLOOD_R2')
  await coordinator.getByLabel('Custom duration').check()
  for (const label of ['Min h', 'Most likely h', 'Max h']) await coordinator.getByLabel(label).fill(label === 'Min h' ? '8' : label === 'Max h' ? '12' : '10')
  await coordinator.getByRole('button', { name: 'Inject disruption' }).click()
  await expect(coordinator.getByText('Disruption injected. Predictions recalculated.')).toBeVisible()
  await expect(row.getByText('High')).toBeVisible()
  await expect(coordinator.getByText(`Risk changed from LOW to HIGH: ${shipmentId}`)).toBeVisible()
  await expect(coordinator.getByText(`Delay risk HIGH: ${shipmentId}`).first()).toBeVisible()
  await expect(coordinator.getByText('Road disruption detected: Flooding - Buldhana market town (Waluj to Amravati road)')).toBeVisible()
  // the customer is told in plain language, with no internal numbers
  await expect(customer.getByText('Why your delivery may be late')).toBeVisible({ timeout: 10_000 })
  await expect(customer.getByText(/road closure on the planned route/).first()).toBeVisible()
  await expect(customer.getByText(/Rs \d/)).toHaveCount(0)
  await coordinator.screenshot({ path: `${SHOTS}/20-coordinator-dashboard.png`, fullPage: true })

  // ---- 6. War Room: compare Continue, Reroute and Split with the real engine; approve ----
  await coordinator.locator('li', { hasText: `Delay risk HIGH: ${shipmentId}` }).getByRole('button', { name: 'War Room' }).first().click()
  await coordinator.getByRole('button', { name: 'Run scenarios' }).click()
  await expect(coordinator.getByText('RECOMMENDED: REROUTE')).toBeVisible()
  await expect(coordinator.getByText('Split is only possible before the vehicle leaves Plant X')).toBeVisible()  // ineligible, with reason
  await coordinator.getByRole('button', { name: 'Approve Reroute' }).click()
  await expect(coordinator.getByText(/Reroute approved and applied/)).toBeVisible()

  // ---- 7. customer gets a safe update; driver and coordinator see the new operational state ----
  await expect(customer.getByText(/Rerouting has been initiated/)).toBeVisible({ timeout: 10_000 })
  await expect(customer.getByText(/rerouted to protect the delivery time/).first()).toBeVisible()
  await expect(driver.getByText(/follow Jalna Ring Road/)).toBeVisible({ timeout: 10_000 })
  await coordinator.getByRole('link', { name: 'Control Tower', exact: true }).click()
  await expect(coordinator.getByText(`Reroute approved: ${shipmentId}`)).toBeVisible()
  await expect(coordinator.locator('tr', { hasText: shipmentId }).getByText(/→ Jalna Ring Road/)).toBeVisible()
  await customer.screenshot({ path: `${SHOTS}/21-customer-portal.png`, fullPage: true })

  // ---- 8. the simulation runs by itself (real backend clock), producing real events ----
  const simBefore = await (await request.get('/api/simulation/clock', { headers: auth })).json()
  await coordinator.getByRole('button', { name: '30×' }).click()
  await coordinator.getByRole('button', { name: 'Start', exact: true }).click()
  await expect(coordinator.getByTestId('sim-status')).toContainText('RUNNING')
  await expect(coordinator.getByText(`Vehicle position updated: ${shipmentId}`).first()).toBeVisible({ timeout: 60_000 })
  const t0 = Date.now()
  let state = ''
  while (Date.now() - t0 < 150_000) {
    state = (await (await request.get(`/api/shipments/${shipmentId}`, { headers: auth })).json()).state
    if (state === 'ARRIVED_AT_CUSTOMER_GATE') break
    const clock = await (await request.get('/api/simulation/clock', { headers: auth })).json()
    if (clock.paused) await request.post('/api/simulation/clock/control', { headers: auth, data: { paused: false } }) // auto-paused on a new high alert
    await coordinator.waitForTimeout(1500)
  }
  expect(state).toBe('ARRIVED_AT_CUSTOMER_GATE')
  await request.post('/api/simulation/clock/control', { headers: auth, data: { paused: true } })
  const simAfter = await (await request.get('/api/simulation/clock', { headers: auth })).json()
  expect(simAfter.sim_now > simBefore.sim_now).toBeTruthy()
  await expect(coordinator.getByText(`${shipmentId} arrived at the customer gate`)).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByTestId('sim-status')).toContainText('PAUSED', { timeout: 10_000 })

  // ---- 9. proof of delivery by the driver completes the delivery; the customer sees it ----
  await expect(card.getByText('Arrived at customer gate').first()).toBeVisible({ timeout: 10_000 })
  await card.getByLabel('Received by (name)').fill('Gate Supervisor')
  await card.getByLabel('Document file').setInputFiles('../docs/demo_files/sample_pod_signed_note.pdf')
  await card.getByRole('button', { name: 'Upload proof of delivery' }).click()
  await expect(driver.getByText(/Delivered\. Received by Gate Supervisor/)).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByText(`Proof of delivery completed for ${shipmentId}`)).toBeVisible({ timeout: 10_000 })
  await customer.getByRole('tab', { name: 'Delivery history' }).click()
  const hist = customer.locator('tr', { hasText: orderId })
  await expect(hist).toBeVisible({ timeout: 10_000 })
  await expect(hist.getByText(/Signed/)).toBeVisible()

  expect(external).toEqual([])
})

test('driver reports a breakdown on the road: coordinator and customer react without reloading', async ({ browser, request }) => {
  const tok = await token(request)
  const auth = { Authorization: `Bearer ${tok}` }
  expect((await request.post('/api/admin/reset', { headers: auth })).ok()).toBeTruthy()
  const coordinator = await login(browser, 'coordinator')
  const customer = await login(browser, 'customer_b')
  const driver = await login(browser, 'driver14', true)

  const row = coordinator.locator('tr', { hasText: 'SHP-AMV-1116-05' })
  await expect(row).toBeVisible()
  await customer.getByRole('button', { name: /ORD-AMV-1116-05/ }).click()
  await driver.getByRole('button', { name: 'Report breakdown' }).click()
  await driver.getByLabel('What happened? (optional)').fill('Tyre burst, waiting for the service truck')
  await driver.getByRole('button', { name: 'Send report' }).click()
  await expect(driver.getByText(/Breakdown reported/).first()).toBeVisible()

  await expect(coordinator.getByText('Driver report on SHP-AMV-1116-05')).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByText(/Tyre burst/).first()).toBeVisible()
  await expect(coordinator.getByText(/(ETA recalculated for SHP-AMV-1116-05: \+\d|Risk changed from \w+ to \w+: SHP-AMV-1116-05)/).first()).toBeVisible()
  await expect(customer.getByText(/disruption was detected affecting your delivery/)).toBeVisible({ timeout: 10_000 })
  await expect(customer.getByText(/Tyre burst/)).toHaveCount(0)             // the driver's note is internal
  // a second report is blocked: the button is gone while a report is active
  await expect(driver.getByRole('button', { name: 'Report breakdown' })).toHaveCount(0)
})

test('the driver app, customer portal and dashboard all render at their intended sizes', async ({ browser, request }) => {
  const tok = await token(request)
  expect((await request.post('/api/admin/reset', { headers: { Authorization: `Bearer ${tok}` } })).ok()).toBeTruthy()
  // a customer on a phone: no horizontal scrolling
  const phone = await login(browser, 'customer_a', true)
  await expect(phone.getByRole('heading', { name: 'My deliveries' })).toBeVisible()
  const overflow = await phone.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)
  expect(overflow).toBeLessThanOrEqual(1)
  // a driver on a phone
  const drv = await login(browser, 'driver1', true)
  await expect(drv.getByRole('navigation', { name: 'Driver navigation' })).toBeVisible()
  expect(await drv.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  await drv.getByRole('button', { name: 'History' }).click()
  await expect(drv.getByText(/recent deliveries/)).toBeVisible()
})
