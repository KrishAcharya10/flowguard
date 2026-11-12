// Read-only check of the RUNNING site (works on any data state: fresh seed or a demo in progress) (http://127.0.0.1:8000): all three roles, every page, no console errors,
// no failed API calls. Run with:  npx playwright test -c playwright.live.config.ts
import { expect, test, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'

async function session(browser: Browser, username: string, mobile = false) {
  const problems: string[] = []
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } })
  opened.push(ctx)
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`) })
  page.on('pageerror', (e) => problems.push(`exception: ${e.message}`))
  page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 400) problems.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`) })
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return { page, problems }
}
const go = async (page: Page, path: string) => { await page.goto(path); await page.waitForLoadState('networkidle') }

test('COORDINATOR: control tower, gate slots, documents, analytics, demo guide', async ({ browser }) => {
  const { page, problems } = await session(browser, 'coordinator')
  await go(page, '/tower')
  await expect(page.getByRole('heading', { name: 'Control Tower' })).toBeVisible()
  await expect(page.getByTestId('sim-status')).toBeVisible()
  await expect(page.getByText('Active orders', { exact: true })).toBeVisible()
  await expect(page.getByText('Gate slots today')).toBeVisible()
  await expect(page.locator('.leaflet-container')).toBeVisible()
  await expect(page.getByText('Live operational activity')).toBeVisible()
  await expect(page.getByRole('button', { name: 'SHP-G1', exact: true }).first()).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/30-coordinator-tower.png`, fullPage: true })

  await go(page, '/gate')
  await expect(page.getByRole('heading', { name: 'Gate slot booking' })).toBeVisible()
  await expect(page.getByTestId('gate-schedule')).toBeVisible()
  await expect(page.getByTestId('slot-07').getByText('Full')).toBeVisible()
  await expect(page.getByText('Weighbridge calibration')).toBeVisible()
  await expect(page.getByText('Upcoming bookings')).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/31-gate-slots.png`, fullPage: true })

  await go(page, '/documents')
  await expect(page.getByRole('heading', { name: 'Invoices and proof of delivery' })).toBeVisible()
  await expect(page.getByTestId('documents-panel')).toBeVisible()
  await expect(page.getByTestId('doc-row-ORD-1003').getByText(/INV-2026-1003/)).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/32-documents.png`, fullPage: true })

  for (const path of ['/shipments/SHP-G1', '/shipments/SHP-G1/war-room', '/analytics', '/demo']) await go(page, path)
  expect(problems).toEqual([])
})

test('CUSTOMER: orders, chat assistant, documents, history', async ({ browser }) => {
  const { page, problems } = await session(browser, 'customer_a')
  await go(page, '/customer')
  await expect(page.getByRole('heading', { name: 'My deliveries' })).toBeVisible()
  await expect(page.getByTestId('order-detail')).toBeVisible()
  await expect(page.getByText('Original promise', { exact: true }).first()).toBeVisible()
  await expect(page.getByTestId('order-documents')).toBeVisible()

  await page.getByRole('button', { name: 'Open the Where is my order chat' }).click()
  const chat = page.getByTestId('chat-panel')
  await chat.getByRole('button', { name: 'Where is my order?' }).click()
  await expect(chat.getByText(/open orders?|Status:|reported position|not left Plant X/).first()).toBeVisible()
  await chat.getByLabel('Your question').fill('Where is ORD-1007?')   // in transit in the seed; may have arrived if the demo was advanced
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/Latest reported position: near|has arrived|was delivered|reached/).last()).toBeVisible()
  await page.screenshot({ path: `${SHOTS}/33-customer-chat.png` })
  await chat.getByRole('button', { name: 'Close chat' }).click()

  await page.getByRole('tab', { name: 'Documents' }).click()
  await expect(page.getByText('invoices available')).toBeVisible()
  await expect(page.getByText('INV-2026-1007').or(page.getByText(/INV-2026-1007\.pdf/)).first()).toBeVisible()
  await page.getByRole('tab', { name: 'Delivery history' }).click()
  await expect(page.getByText(/On time|late/).first()).toBeVisible()
  await go(page, '/tower')
  await expect(page).toHaveURL(/\/customer$/)
  expect(problems).toEqual([])
})

test('DRIVER: deliveries, gate appointment, history (phone size)', async ({ browser }) => {
  const { page, problems } = await session(browser, 'driver1', true)
  await go(page, '/driver')
  await expect(page.getByRole('heading', { name: 'My deliveries' })).toBeVisible()
  await expect(page.getByTestId('driver-card-SHP-G1')).toBeVisible()
  await expect(page.getByTestId('gate-appointment')).toBeVisible()
  await expect(page.getByText(/Gate 2/).first()).toBeVisible()
  await expect(page.getByTestId('gate-appointment').getByText(/BOOKED|CHECKED IN|COMPLETED|MISSED|CANCELLED/).first()).toBeVisible()   // state depends on how far the demo was advanced
  await page.screenshot({ path: `${SHOTS}/34-driver-app.png`, fullPage: true })
  await page.getByRole('button', { name: 'History' }).click()
  await expect(page.getByText(/recent deliveries/)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1)
  expect(problems).toEqual([])
})
