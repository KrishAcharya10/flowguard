// The three bonus features through the real frontend: gate slot booking, the customer chat assistant,
// invoice and proof-of-delivery upload / download. Separate browser contexts per role; no reloads after login.
import { readFileSync } from 'node:fs'
import { expect, test, type APIRequestContext, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'
const SHOTS = '../docs/screenshots'
const FILES = '../docs/demo_files'

async function login(browser: Browser, username: string, mobile = false): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, acceptDownloads: true } : { viewport: { width: 1440, height: 900 }, acceptDownloads: true })
  opened.push(ctx)
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return page
}
const token = async (r: APIRequestContext, user: string) =>
  (await (await r.post('/api/auth/login', { data: { username: user, password: PASSWORD } })).json()).access_token as string
const hdr = (t: string) => ({ Authorization: `Bearer ${t}` })

test.describe.configure({ mode: 'serial' })

test('GATE BOOKING: coordinator books, reschedules; driver sees it and checks in; capacity follows', async ({ browser, request }) => {
  test.setTimeout(180_000)
  const co = await token(request, 'coordinator')
  expect((await request.post('/api/admin/reset', { headers: hdr(co) })).ok()).toBeTruthy()
  const order = await (await request.post('/api/orders', { headers: hdr(co), data: { route_id: 'R2', transporter_id: 'TR-1', product_code: 'FILM-L30', quantity_tonnes: 20, loading_in_h: 4 } })).json()
  const sid: string = order.shipment_id

  const coordinator = await login(browser, 'coordinator')
  await coordinator.getByRole('link', { name: 'Gate slots' }).click()
  await expect(coordinator.getByRole('heading', { name: 'Gate slot booking' })).toBeVisible()
  const row8 = coordinator.getByTestId('slot-08')
  await expect(row8).toContainText('0/3')

  // 1. coordinator books a gate slot for the new shipment
  await row8.getByRole('button', { name: 'Book', exact: true }).click()
  const dialog = coordinator.getByRole('dialog', { name: /Book a gate slot/ })
  await dialog.getByLabel('Shipment', { exact: true }).selectOption(sid)
  await expect(dialog.getByText(order.vehicle_label.replace(' (fictional)', ''))).toBeVisible()
  await dialog.getByRole('button', { name: 'Book slot' }).click()
  await expect(row8).toContainText('1/3')
  await expect(row8.getByText(sid)).toBeVisible()
  await expect(row8.getByText('BOOKED')).toBeVisible()
  await expect(coordinator.getByTestId('slot-07').getByText('Full')).toBeVisible()                       // seeded full slot
  await coordinator.screenshot({ path: `${SHOTS}/40-gate-booking.png`, fullPage: true })

  // overbooking is visible: lower the capacity of the full 07:00 slot
  await coordinator.getByTestId('slot-07').getByRole('button', { name: /Settings for 07:00/ }).click()
  const edit = coordinator.getByRole('dialog', { name: /Slot settings/ })
  await edit.getByLabel('Capacity (vehicles)').fill('1')
  await expect(edit.getByText(/overbooked/)).toBeVisible()
  await edit.getByRole('button', { name: 'Save' }).click()
  await expect(coordinator.getByTestId('slot-07').getByText('Overbooked')).toBeVisible()

  // 2. the driver sees the appointment (no reload), but cannot check in yet
  const driver = await login(browser, order.driver_username, true)
  const appt = driver.getByTestId('gate-appointment')
  await expect(appt).toBeVisible()
  await expect(appt.getByText('BOOKED')).toBeVisible()
  await expect(appt.getByText(/Gate 2/)).toBeVisible()
  await expect(appt.getByRole('button', { name: 'Check in at the gate' })).toBeDisabled()
  await expect(appt.getByText(/Check-in opens at/)).toBeVisible()

  // 3. reschedule: the old place is released and the new one is taken
  await row8.getByRole('button', { name: 'Reschedule' }).click()
  const move = coordinator.getByRole('dialog', { name: new RegExp(`Reschedule ${sid}`) })
  await move.getByLabel('New slot').selectOption({ label: /10:00 IST/ as unknown as string }).catch(async () => {
    const opts = await move.getByLabel('New slot').locator('option').allTextContents()
    const target = opts.find((o) => o.includes('10:00 IST'))!
    await move.getByLabel('New slot').selectOption({ label: target })
  })
  await move.getByRole('button', { name: 'Reschedule' }).click()
  await expect(row8).toContainText('0/3')
  await expect(coordinator.getByTestId('slot-10')).toContainText('1/3')
  await expect(appt.getByText(/10:00 IST/)).toBeVisible({ timeout: 10_000 })

  // 4. the simulation clock moves close to the slot; the driver checks in
  expect((await request.post('/api/simulation/clock/advance', { headers: hdr(co), data: { minutes: 180 } })).ok()).toBeTruthy()   // 09:00 IST
  await expect(appt.getByRole('button', { name: 'Check in at the gate' })).toBeEnabled({ timeout: 10_000 })
  await appt.getByRole('button', { name: 'Check in at the gate' }).click()
  await expect(appt.getByText(/You are checked in/)).toBeVisible()
  await driver.screenshot({ path: `${SHOTS}/41-driver-gate-checkin.png`, fullPage: true })

  // 5. the coordinator sees the new status; capacity is unchanged by check-in
  await expect(coordinator.getByTestId('slot-10').getByText('CHECKED IN')).toBeVisible({ timeout: 10_000 })
  await expect(coordinator.getByTestId('slot-10')).toContainText('1/3')
  await expect(coordinator.getByText(`Gate slot rescheduled for ${sid}`).or(coordinator.getByText(sid).first())).toBeVisible()
})

test('CHATBOT: customer asks about their order; another customer\'s order cannot be reached', async ({ browser, request }) => {
  expect((await request.post('/api/admin/reset', { headers: hdr(await token(request, 'coordinator')) })).ok()).toBeTruthy()
  const a = await login(browser, 'customer_a')
  await a.getByRole('button', { name: 'Open the Where is my order chat' }).click()
  const chat = a.getByTestId('chat-panel')
  await chat.getByRole('button', { name: 'Where is my order?' }).click()
  await expect(chat.getByText(/You have 4 open orders/)).toBeVisible()
  // a specific order: real status, position with timestamp, ETA range
  await chat.getByLabel('Your question').fill('Where is ORD-1007?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/Latest reported position: near/).last()).toBeVisible()
  await expect(chat.getByText(/Reported .* IST \(simulated\)/)).toBeVisible()
  await chat.getByLabel('Your question').fill('When will ORD-1007 arrive?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/most likely between/)).toBeVisible()
  await chat.getByLabel('Your question').fill('What was the original promised delivery for ORD-1007?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/original promised delivery for ORD-1007 is/)).toBeVisible()
  // another customer's order and commercial questions are refused
  await chat.getByLabel('Your question').fill('Where is ORD-1003?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/I could not find an order ORD-1003 on your account/)).toBeVisible()
  await expect(chat.getByText(/Eastgate|FILM-L30/)).toHaveCount(0)
  await chat.getByLabel('Your question').fill('What freight cost and penalty do you pay?')
  await chat.getByRole('button', { name: 'Send' }).click()
  await expect(chat.getByText(/I cannot share internal commercial information/)).toBeVisible()
  await expect(chat.getByText(/Rs \d/)).toHaveCount(0)
  await a.screenshot({ path: `${SHOTS}/42-customer-chat.png` })

  const b = await login(browser, 'customer_b')
  await b.getByRole('button', { name: 'Open the Where is my order chat' }).click()
  const chatB = b.getByTestId('chat-panel')
  await chatB.getByLabel('Your question').fill('Where is ORD-1003?')
  await chatB.getByRole('button', { name: 'Send' }).click()
  await expect(chatB.getByText(/Latest reported position: near/)).toBeVisible()
  await chatB.getByLabel('Your question').fill('Where is ORD-1007?')               // belongs to customer A
  await chatB.getByRole('button', { name: 'Send' }).click()
  await expect(chatB.getByText(/I could not find an order ORD-1007 on your account/)).toBeVisible()
})

test('INVOICE AND POD: upload, replace, verify and download across the three roles; other customers are refused', async ({ browser, request }) => {
  test.setTimeout(180_000)
  const co = await token(request, 'coordinator')
  expect((await request.post('/api/admin/reset', { headers: hdr(co) })).ok()).toBeTruthy()

  // ---- coordinator uploads an invoice against ORD-G1 ----
  const coordinator = await login(browser, 'coordinator')
  await coordinator.getByRole('link', { name: 'Documents', exact: true }).click()
  await coordinator.getByTestId('doc-row-ORD-G1').click()
  const panel = coordinator.getByTestId('documents-panel')
  await expect(panel.getByText('No invoice has been uploaded for this order yet.')).toBeVisible()
  await panel.getByLabel('Document file').setInputFiles(`${FILES}/sample_invoice.pdf`)
  await panel.getByLabel('Invoice number (optional)').fill('INV-DEMO-0001')
  await panel.getByRole('button', { name: 'Upload invoice' }).click()
  await expect(panel.getByText(/Invoice version 1 uploaded for ORD-G1/)).toBeVisible()
  await expect(panel.getByText('sample_invoice.pdf')).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/43-invoice-management.png`, fullPage: true })

  // ---- the customer sees it (no reload) and downloads exactly that file ----
  const customer = await login(browser, 'customer_a')
  await customer.getByRole('tab', { name: 'Documents' }).click()
  const card = customer.locator('section', { hasText: 'Order ORD-G1' })
  await expect(card.getByText('sample_invoice.pdf')).toBeVisible({ timeout: 10_000 })
  const [dl] = await Promise.all([customer.waitForEvent('download'), card.getByRole('button', { name: 'Download' }).first().click()])
  expect(dl.suggestedFilename()).toBe('sample_invoice.pdf')
  const got = readFileSync(await dl.path()!)
  expect(got.equals(readFileSync(`${FILES}/sample_invoice.pdf`))).toBeTruthy()
  await customer.screenshot({ path: `${SHOTS}/44-customer-documents.png`, fullPage: true })

  // ---- replacement needs a reason and creates version 2; the customer sees only the new one ----
  await panel.getByLabel('Document file').setInputFiles(`${FILES}/sample_invoice_corrected.pdf`)
  await expect(panel.getByRole('button', { name: 'Replace invoice (new version)' })).toBeDisabled()
  await panel.getByLabel('Reason for replacing (required)').fill('Quantity was wrong on the first invoice')
  await panel.getByRole('button', { name: 'Replace invoice (new version)' }).click()
  await expect(panel.getByText(/Invoice version 2 uploaded/)).toBeVisible()
  await expect(card.getByText('sample_invoice_corrected.pdf')).toBeVisible({ timeout: 10_000 })
  await expect(card.getByText('sample_invoice.pdf', { exact: true })).toHaveCount(0)

  // ---- another customer cannot see or fetch it ----
  const b = await token(request, 'customer_b')
  const mine = await (await request.get('/api/customer/me/documents', { headers: hdr(b) })).json()
  expect(mine.every((d: { order_id: string }) => d.order_id !== 'ORD-G1')).toBeTruthy()
  const a = await token(request, 'customer_a')
  const aDocs = await (await request.get('/api/customer/me/documents', { headers: hdr(a) })).json()
  const g1 = aDocs.find((d: { order_id: string }) => d.order_id === 'ORD-G1')
  expect((await request.get(`/api/documents/${g1.id}/download`, { headers: hdr(b) })).status()).toBe(404)
  expect((await request.get(`/api/documents/${g1.id}/download`)).status()).toBe(401)

  // ---- the driver uploads the proof of delivery after reaching the customer gate (SHP-1011 has arrived) ----
  const driver = await login(browser, 'driver11', true)
  const dcard = driver.getByTestId('driver-card-SHP-1011')
  await expect(dcard.getByText('Proof of delivery', { exact: true })).toBeVisible()
  await expect(dcard.getByRole('button', { name: 'Upload proof of delivery' })).toBeDisabled()
  await dcard.getByLabel('Received by (name)').fill('Anita Rao')
  await dcard.getByLabel('Document file').setInputFiles(`${FILES}/sample_pod_photo.png`)
  await dcard.getByRole('button', { name: 'Upload proof of delivery' }).click()
  await expect(driver.getByText(/Delivered\. Received by Anita Rao/)).toBeVisible()
  await expect(dcard.getByText('sample_pod_photo.png')).toBeVisible()
  await driver.screenshot({ path: `${SHOTS}/45-driver-pod-upload.png`, fullPage: true })

  // ---- the coordinator sees the POD and verifies that it belongs to the right shipment ----
  await coordinator.getByTestId('doc-row-ORD-1011').click()
  await expect(panel.getByText('sample_pod_photo.png')).toBeVisible({ timeout: 10_000 })
  await expect(panel.getByText(/Received by Anita Rao/)).toBeVisible()
  await panel.getByRole('button', { name: 'Verify' }).click()
  await expect(panel.getByRole('button', { name: 'Confirm verification' })).toBeDisabled()
  await panel.getByLabel(/I checked that this document belongs to/).check()
  await panel.getByRole('button', { name: 'Confirm verification' }).click()
  await expect(panel.getByText('✓ Verified').first()).toBeVisible()
  await coordinator.screenshot({ path: `${SHOTS}/46-pod-management.png`, fullPage: true })

  // ---- the owning customer downloads the POD; others are refused ----
  const cc = await login(browser, 'customer_c')
  await cc.getByRole('tab', { name: 'Documents' }).click()
  const podCard = cc.locator('section', { hasText: 'Order ORD-1011' })
  await expect(podCard.getByText('sample_pod_photo.png')).toBeVisible({ timeout: 10_000 })
  const [pod] = await Promise.all([cc.waitForEvent('download'), podCard.getByRole('button', { name: 'Download' }).last().click()])
  expect(readFileSync(await pod.path()!).equals(readFileSync(`${FILES}/sample_pod_photo.png`))).toBeTruthy()
  const cDocs = await (await request.get('/api/customer/me/documents', { headers: hdr(await token(request, 'customer_c')) })).json()
  const podDoc = cDocs.find((d: { kind: string }) => d.kind === 'POD')
  expect((await request.get(`/api/documents/${podDoc.id}/download`, { headers: hdr(a) })).status()).toBe(404)
  expect((await request.get(`/api/documents/${podDoc.id}/download`, { headers: hdr(b) })).status()).toBe(404)

  // ---- invalid files are rejected by the server even if the browser lets them through ----
  const bad = await request.post('/api/orders/ORD-1004/invoice?filename=fake.pdf', { headers: { ...hdr(co), 'Content-Type': 'application/pdf' }, data: Buffer.from('not really a pdf') })
  expect(bad.status()).toBe(415)
  // ---- and everything was audited ----
  const audit = await (await request.get('/api/audit-events?limit=200', { headers: hdr(co) })).json()
  const actions = new Set(audit.map((x: { action: string }) => x.action))
  for (const needed of ['DOCUMENT_UPLOADED', 'DOCUMENT_REPLACED', 'POD_DOCUMENT_UPLOADED', 'POD_VERIFIED', 'DOCUMENT_DOWNLOADED']) expect(actions.has(needed)).toBeTruthy()
})
