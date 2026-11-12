// Visual tour of the running site (port 8000): screenshots of every role and the main screens, desktop and phone.
// Read-only. Output: docs/screenshots/redesign/. Run:  npx playwright test -c playwright.live.config.ts e2e-live/tour.spec.ts
import { expect, test, type Browser, type Page } from '@playwright/test'

const OUT = '../docs/screenshots/redesign'
const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'

async function login(browser: Browser, username: string, size = { width: 1440, height: 900 }, mobile = false): Promise<Page> {
  const ctx = await browser.newContext(mobile ? { viewport: size, isMobile: true, hasTouch: true } : { viewport: size })
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill(username)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return page
}

test('login page', async ({ browser }) => {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.waitForTimeout(600)
  await page.screenshot({ path: `${OUT}/10-login.png` })
  await ctx.close()
})

test('coordinator screens', async ({ browser }) => {
  const p = await login(browser, 'coordinator')
  await expect(p.getByTestId('fleet-map')).toBeVisible()
  await p.waitForTimeout(3500)                                       // let tiles / the offline network settle
  await p.screenshot({ path: `${OUT}/01-control-tower.png` })
  await p.screenshot({ path: `${OUT}/01b-control-tower-full.png`, fullPage: true })
  for (const [name, path] of [
    ['04-analytics', 'Analytics'], ['05-gate-slots', 'Gate slots'],
    ['06-documents', 'Documents'], ['07-demo-guide', 'Demo guide'],
  ] as const) {
    await p.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: path }).click()
    await p.waitForTimeout(2200)
    await p.screenshot({ path: `${OUT}/${name}.png`, fullPage: true })
  }
  await p.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Control Tower' }).click()
  await p.getByRole('table').getByRole('button', { name: 'SHP-PTH-1116-01', exact: true }).click()
  await p.waitForTimeout(1800)
  await p.screenshot({ path: `${OUT}/03-shipment-detail.png`, fullPage: true })
  await p.locator('a,button').filter({ hasText: /War Room/ }).first().click()
  await p.waitForTimeout(1500)
  await p.screenshot({ path: `${OUT}/08-war-room-before.png`, fullPage: true })
  await p.context().close()
})

test('customer and driver', async ({ browser }) => {
  const c = await login(browser, 'customer_a')
  await c.waitForTimeout(2500)
  await c.screenshot({ path: `${OUT}/09-customer.png`, fullPage: true })
  await c.context().close()
  const cm = await login(browser, 'customer_a', { width: 390, height: 844 }, true)
  await cm.waitForTimeout(2500)
  await cm.screenshot({ path: `${OUT}/09b-customer-phone.png`, fullPage: true })
  await cm.context().close()
  const d = await login(browser, 'driver1', { width: 390, height: 844 }, true)
  await d.waitForTimeout(1500)
  await d.screenshot({ path: `${OUT}/11-driver-phone.png`, fullPage: true })
  await d.context().close()
})
