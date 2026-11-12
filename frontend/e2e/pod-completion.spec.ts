// The "I cannot finish the delivery" bug: a vehicle arrives and the delivery asks for proof of delivery,
// but the driver could not find where to give it and nobody else could complete it. Both ways out are tested:
// the driver finishes (with or without a document) and the control tower finishes it for the driver.
import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test'

const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'
const FILES = '../docs/demo_files'

async function login(browser: Browser, username: string, mobile = false): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : { viewport: { width: 1440, height: 900 } })
  opened.push(ctx)
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return page
}
const coordToken = async (r: APIRequestContext) =>
  (await (await r.post('/api/auth/login', { data: { username: 'coordinator', password: PASSWORD } })).json()).access_token as string
const reset = async (r: APIRequestContext) => expect((await r.post('/api/admin/reset', { headers: { Authorization: `Bearer ${await coordToken(r)}` } })).ok()).toBeTruthy()

test.describe.configure({ mode: 'serial' })

test('DRIVER: the hand-over form is the first thing on an arrived card, and works with no document', async ({ browser, request }) => {
  test.setTimeout(120_000)
  await reset(request)
  const driver = await login(browser, 'driver11', true)          // Santosh Bhosale, SHP-BHW-1116-02 has arrived
  const card = driver.getByTestId('driver-card-SHP-BHW-1116-02')
  const handover = card.getByTestId('handover')
  await expect(handover).toBeVisible()
  await expect(handover.getByText('You have arrived. Hand over the delivery')).toBeVisible()
  // the buttons are explained, not silently disabled
  await expect(handover.getByRole('button', { name: 'Upload proof of delivery' })).toBeDisabled()
  await expect(handover.getByRole('status')).toContainText("enter the receiver's name")
  await expect(handover.getByRole('button', { name: 'Complete delivery without a document' })).toBeDisabled()
  await handover.getByLabel('Received by (name)').fill('Ravi Kumar')
  await expect(handover.getByRole('status')).toContainText('photo or signed note')
  await expect(handover.getByRole('button', { name: 'Complete delivery without a document' })).toBeEnabled()
  await driver.screenshot({ path: `${SHOTS}/47-driver-handover.png`, fullPage: true })
  await handover.getByRole('button', { name: 'Complete delivery without a document' }).click()
  await expect(driver.getByText(/Delivered\. Received by Ravi Kumar/)).toBeVisible({ timeout: 10_000 })
  await expect(handover).toHaveCount(0)
})

test('COORDINATOR: completes the delivery for the driver, from the Control Tower row and from Documents', async ({ browser, request }) => {
  test.setTimeout(120_000)
  await reset(request)
  const coordinator = await login(browser, 'coordinator')
  // the arrived load is called out at the top of Documents and has its own action in the Control Tower table
  const row = coordinator.getByRole('row', { name: /SHP-BHW-1116-02/ })
  await expect(row.getByRole('button', { name: 'Add proof of delivery' })).toBeVisible({ timeout: 15_000 })
  await row.getByRole('button', { name: 'Add proof of delivery' }).click()
  await expect(coordinator.getByRole('heading', { name: 'Invoices and proof of delivery' })).toBeVisible()
  await expect(coordinator.getByText(/waiting for proof of delivery/)).toBeVisible()
  const box = coordinator.getByTestId('on-behalf-SHP-BHW-1116-02')
  await expect(box).toBeVisible()
  await expect(box.getByRole('button', { name: 'Complete without a document' })).toBeDisabled()
  await box.getByLabel('Who received the delivery?').fill('Gate Supervisor')
  await coordinator.screenshot({ path: `${SHOTS}/48-coordinator-complete-delivery.png`, fullPage: true })
  await box.getByRole('button', { name: 'Complete without a document' }).click()
  await expect(coordinator.getByText('Delivery completed without a document.')).toBeVisible({ timeout: 10_000 })

  // the driver's phone now shows the finished delivery, and the history says who did it
  const driver = await login(browser, 'driver11', true)
  await expect(driver.getByText(/Delivered\. Received by Gate Supervisor/)).toBeVisible({ timeout: 10_000 })
  const events = await (await request.get('/api/shipments/SHP-BHW-1116-02/events', { headers: { Authorization: `Bearer ${await coordToken(request)}` } })).json()
  expect(events.some((e: { note: string }) => /recorded by the control tower/.test(e.note))).toBeTruthy()
})

test('COORDINATOR: can add the document later, after completing without one', async ({ browser, request }) => {
  test.setTimeout(120_000)
  await reset(request)
  const coordinator = await login(browser, 'coordinator')
  await coordinator.goto('/documents?order=ORD-BHW-1116-02')
  const box = coordinator.getByTestId('on-behalf-SHP-BHW-1116-02')
  await box.getByLabel('Who received the delivery?').fill('Gate Supervisor')
  await box.getByLabel('Document file').setInputFiles(`${FILES}/sample_pod_photo.png`)
  await box.getByRole('button', { name: 'Upload and complete delivery' }).click()
  // the form has done its job and is replaced by the stored document and the recipient
  await expect(coordinator.getByText('sample_pod_photo.png').first()).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByText(/Received by Gate Supervisor/)).toBeVisible()
  await expect(box).toHaveCount(0)
})
