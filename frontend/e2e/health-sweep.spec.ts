// Health sweep: opens every page as each role and FAILS on any console error, uncaught exception or
// failed API call (4xx/5xx). This is the "is anything actually broken" check, not a pixel check.
import { expect, test, type Browser, type Page } from '@playwright/test'

// close every browser window when a test ends, so old pages stop polling the server
const opened: import('@playwright/test').BrowserContext[] = []
test.afterEach(async () => { await Promise.all(opened.splice(0).map((c) => c.close())) })

const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'

async function session(browser: Browser, username: string) {
  const problems: string[] = []
  const ctx = await browser.newContext({ viewport: username.startsWith('driver') ? { width: 390, height: 844 } : { width: 1440, height: 900 } })
  opened.push(ctx)
  const page = await ctx.newPage()
  page.on('console', (m) => { if (m.type() === 'error') problems.push(`console: ${m.text()}`) })
  page.on('pageerror', (e) => problems.push(`exception: ${e.message}`))
  page.on('response', (r) => {
    if (r.url().includes('/api/') && r.status() >= 400) problems.push(`${r.status()} ${r.request().method()} ${new URL(r.url()).pathname}`)
  })
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' })).toBeVisible()
  return { page, problems }
}

async function visit(page: Page, path: string) {
  await page.goto(path)
  await page.waitForLoadState('networkidle')
  await expect(page.locator('body')).not.toContainText('Could not load')
}

test('coordinator: every page loads without errors', async ({ browser, request }) => {
  const tok = (await (await request.post('/api/auth/login', { data: { username: 'coordinator', password: PASSWORD } })).json()).access_token
  await request.post('/api/admin/reset', { headers: { Authorization: `Bearer ${tok}` } })
  const { page, problems } = await session(browser, 'coordinator')
  for (const p of ['/tower', '/shipments/SHP-PTH-1116-01', '/shipments/SHP-PTH-1116-01/war-room', '/analytics', '/demo']) await visit(page, p)
  expect(problems).toEqual([])
})

test('customer: every page loads without errors', async ({ browser }) => {
  const { page, problems } = await session(browser, 'customer_a')
  await visit(page, '/customer')
  await visit(page, '/tower') // must bounce back to the customer's own page
  await expect(page).toHaveURL(/\/customer$/)
  expect(problems).toEqual([])
})

test('driver: every page loads without errors', async ({ browser }) => {
  const { page, problems } = await session(browser, 'driver1')
  await visit(page, '/driver')
  expect(problems).toEqual([])
})
