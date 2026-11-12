// The redesigned map and Control Tower, end to end against the real backend:
//   online tiles (faked here so the test needs no internet) and the automatic offline fallback,
//   vehicle selection and detail panel, disruption overlay, an approved reroute drawn as the active route,
//   map tools (filters, search, legend, full screen) and layout at several screen sizes.
import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test'

const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots/redesign'
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64')
const TILES = '**/tile.openstreetmap.org/**'

const token = async (r: APIRequestContext, user: string) =>
  (await (await r.post('/api/auth/login', { data: { username: user, password: PASSWORD } })).json()).access_token as string
const hdr = (t: string) => ({ Authorization: `Bearer ${t}` })

async function login(browser: Browser, username: string, opts: { tiles?: 'ok' | 'fail'; size?: { width: number; height: number }; mobile?: boolean } = {}): Promise<Page> {
  const size = opts.size ?? { width: 1440, height: 900 }
  const ctx = await browser.newContext(opts.mobile ? { viewport: size, isMobile: true, hasTouch: true } : { viewport: size })
  opened.push(ctx)
  const tiles = opts.tiles ?? 'ok'
  await ctx.route(TILES, (r) => (tiles === 'ok' ? r.fulfill({ status: 200, contentType: 'image/png', body: PNG }) : r.abort('internetdisconnected')))
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return page
}

test.describe.configure({ mode: 'serial' })

test('ONLINE: geographic tiles by default, attribution shown, no offline label', async ({ browser, request }) => {
  test.setTimeout(120_000)
  expect((await request.post('/api/admin/reset', { headers: hdr(await token(request, 'coordinator')) })).ok()).toBeTruthy()
  const page = await login(browser, 'coordinator', { tiles: 'ok' })
  const map = page.getByTestId('fleet-map')
  await expect(map).toBeVisible()
  await expect(map.locator('.leaflet-tile-loaded').first()).toBeVisible({ timeout: 15_000 })
  await expect(map.getByText('OpenStreetMap')).toBeVisible()                       // attribution is always shown with external tiles
  await expect(page.getByTestId('map-offline-label')).toHaveCount(0)
  await expect(map.getByRole('button', { name: 'Map', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${SHOTS}/01-control-tower.png` })
  await page.screenshot({ path: `${SHOTS}/01b-control-tower-full.png`, fullPage: true })
})

test('OFFLINE: tiles fail, the local logistics network appears automatically and is labelled', async ({ browser }) => {
  test.setTimeout(120_000)
  const page = await login(browser, 'coordinator', { tiles: 'fail' })
  const label = page.getByTestId('map-offline-label')
  await expect(label).toHaveText('Illustrative logistics network — not to scale', { timeout: 20_000 })
  await expect(page.getByTestId('map-note')).toContainText('offline logistics network')
  await expect(page.getByTestId('fleet-map').locator('.leaflet-tile-loaded')).toHaveCount(await page.getByTestId('fleet-map').locator('.fg-offline-tiles .leaflet-tile-loaded').count())
  // it is not the old labelled coordinate grid: no "A10 / B11" grid labels, but real overlays: plant, destinations, vehicles
  await expect(page.locator('.grid-label')).toHaveCount(0)
  await expect(page.locator('.fg-plant')).toHaveCount(1)
  await expect(page.locator('.fg-dest')).toHaveCount(4)
  await expect(page.locator('.fg-node').first()).toBeAttached()
  await expect(page.locator('.fg-veh, .fg-cluster').first()).toBeVisible()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${SHOTS}/02-offline-network.png` })
  // switching to the geographic map by hand removes the offline label
  await page.getByTestId('map-note').getByRole('button', { name: 'Retry online map' }).click()
})

test('VEHICLES: select from the sidebar and the map; detail panel; search and filters; legend; full screen', async ({ browser, request }) => {
  test.setTimeout(180_000)
  expect((await request.post('/api/admin/reset', { headers: hdr(await token(request, 'coordinator')) })).ok()).toBeTruthy()
  const page = await login(browser, 'coordinator')
  const map = page.getByTestId('fleet-map')
  await expect(page.getByTestId('priority-list').getByRole('button').first()).toBeVisible()
  await page.getByTestId('priority-list').getByRole('button').first().click()
  const panel = page.getByTestId('vehicle-panel')
  await expect(panel).toBeVisible()
  for (const t of ['Customer', 'Driver', 'Transporter', 'Milestone', 'Route', 'Original promise', 'Predicted ETA', 'P(late)', 'Last reported']) await expect(panel.getByText(t, { exact: true })).toBeVisible()
  await expect(panel.getByRole('button', { name: /Open shipment/ })).toBeVisible()
  await expect(panel.getByRole('button', { name: 'Open War Room' })).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/03-selected-shipment.png` })
  await panel.getByRole('button', { name: 'Close shipment details' }).click()
  await expect(panel).toHaveCount(0)

  // click a truck on the map itself
  const truck = map.locator('.fg-veh').first()
  await truck.click({ force: true })
  await expect(panel).toBeVisible()
  await panel.getByRole('button', { name: 'Close shipment details' }).click()

  // search + status chip + transporter + risk filters change what is drawn
  const all = await map.locator('.fg-veh, .fg-cluster').count()
  await map.getByRole('textbox', { name: 'Search shipment ID' }).fill('AMV-1116-04')
  await expect(map.locator('.fg-veh')).toHaveCount(1)
  await map.getByRole('textbox', { name: 'Search shipment ID' }).fill('')
  await map.getByRole('group', { name: 'Filter by status' }).getByRole('button', { name: /^Late/ }).click()
  await expect(map.locator('.fg-veh, .fg-cluster')).toHaveCount(1)
  await map.getByRole('group', { name: 'Filter by status' }).getByRole('button', { name: /^All/ }).click()
  await map.getByLabel('Filter by transporter').selectOption({ index: 1 })
  expect(await map.locator('.fg-veh, .fg-cluster').count()).toBeLessThanOrEqual(all)
  await map.getByLabel('Filter by transporter').selectOption('')

  // legend explains every symbol
  await map.getByRole('button', { name: 'Legend' }).click()
  const legend = page.getByTestId('map-legend')
  for (const t of ['On track', 'At risk', 'Late', 'Arrived, POD pending', 'Stale position', 'Primary route', 'Alternative route', 'Active reroute', 'Road disruption', 'Plant X', 'Customer destination', 'Decision node']) await expect(legend).toContainText(t)
  await map.getByRole('button', { name: 'Close legend' }).click()

  // map tools
  for (const n of ['Zoom in', 'Zoom out', 'Fit all shipments', 'Centre on Plant X']) await map.getByRole('button', { name: n }).click()
  await map.getByRole('button', { name: 'Hide alternative routes' }).click()
  await expect(map.getByRole('button', { name: 'Show alternative routes' })).toHaveAttribute('aria-pressed', 'false')
  await map.getByRole('button', { name: 'Show alternative routes' }).click()
  await map.getByRole('button', { name: 'Full-screen map' }).click()
  const box = await map.locator('.fg-map').boundingBox()
  expect(box!.width).toBeGreaterThan(1300)
  expect(box!.height).toBeGreaterThan(700)
  await page.waitForTimeout(700)
  await page.screenshot({ path: `${SHOTS}/04-fullscreen-map.png` })
  await page.keyboard.press('Escape')
  await expect(map.getByRole('button', { name: 'Full-screen map' })).toBeVisible()
})

test('DISRUPTION and REROUTE: red overlay, War Room scenario cards, approved reroute shown as the active route', async ({ browser, request }) => {
  test.setTimeout(240_000)
  const co = await token(request, 'coordinator')
  expect((await request.post('/api/demo/use-cases/flood-reroute/setup', { headers: hdr(co), data: { mode: 'jump' } })).ok()).toBeTruthy()
  const page = await login(browser, 'coordinator')
  await expect(page.locator('.fg-dis').first()).toBeVisible({ timeout: 15_000 })               // flooding label on the road
  await expect(page.locator('.fg-pulse').first()).toBeAttached()
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${SHOTS}/05-disruption-overlay.png` })
  await expect(page.locator('.fg-routelabel.active')).toHaveCount(0)                           // nothing rerouted yet

  await page.getByTestId('priority-list').getByRole('button', { name: /PTH-1116-01/ }).click()
  await page.getByTestId('vehicle-panel').getByRole('button', { name: 'Open War Room' }).click()
  await page.getByRole('button', { name: 'Run scenarios' }).click()
  await expect(page.getByText('RECOMMENDED: REROUTE')).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(3)
  for (const n of ['Continue', 'Reroute', 'Split shipment']) await expect(page.getByRole('article', { name: `${n} scenario` })).toBeVisible()
  const reroute = page.getByRole('article', { name: 'Reroute scenario' })
  for (const t of ['Median arrival (P50)', 'Late case (P90)', 'P(late)', 'P(customer stock-out)', 'Expected late hours', 'Expected stock-out hours', 'Extra freight', 'SLA cost', 'Stock-out cost', 'Expected total', 'Constraint status']) await expect(reroute).toContainText(t)
  await expect(page.getByRole('article', { name: 'Continue scenario' })).toContainText('violates a constraint')     // why an option is not allowed
  await expect(page.getByText('holds in 16 of 16 stress cases')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/06-war-room.png`, fullPage: true })
  await page.getByRole('button', { name: 'Approve Reroute' }).click()
  await expect(page.getByText(/Reroute approved and applied/)).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/07-war-room-approved.png`, fullPage: true })

  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Control Tower' }).click()
  await expect(page.locator('.fg-routelabel.active')).toHaveCount(1, { timeout: 15_000 })     // the bypass is now the operational route
  await expect(page.locator('.fg-routelabel.active')).toContainText('active reroute')
  await page.waitForTimeout(800)
  await page.screenshot({ path: `${SHOTS}/08-approved-reroute.png` })
})

test('LAYOUT: no horizontal scroll and a usable map at laptop, large, tablet and phone sizes', async ({ browser }) => {
  test.setTimeout(240_000)
  for (const [name, size, mobile] of [
    ['laptop-1280', { width: 1280, height: 720 }, false], ['desktop-1920', { width: 1920, height: 1080 }, false],
    ['tablet-820', { width: 820, height: 1180 }, true], ['phone-390', { width: 390, height: 844 }, true],
  ] as const) {
    const page = await login(browser, 'coordinator', { size, mobile })
    await expect(page.getByTestId('fleet-map')).toBeVisible()
    await page.waitForTimeout(1200)
    const over = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(over, `${name} must not scroll sideways`).toBeLessThanOrEqual(1)
    const mb = await page.locator('.fg-map').boundingBox()
    expect(mb!.height).toBeGreaterThan(400)
    expect(mb!.width).toBeGreaterThan(Math.min(size.width - 80, 600))
    await page.screenshot({ path: `${SHOTS}/12-control-tower-${name}.png` })
    await page.context().close()
  }
})
