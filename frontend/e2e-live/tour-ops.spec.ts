// Screenshot tour of a flood, a War Room decision and an approved reroute on the RUNNING site (port 8000), with the
// real OpenStreetMap tiles. This one CHANGES the live data (it jumps to demo use case 1 and approves the reroute), so
// reset the demo data afterwards (Reset demo in the Control Tower, or python -m app.seed.reset).
import { expect, test, type Browser, type Page } from '@playwright/test'

const OUT = '../docs/screenshots/redesign'
const PASSWORD = process.env.FLOWGUARD_DEMO_PASSWORD ?? 'PlantX-demo-2026'

async function login(browser: Browser, offline = false): Promise<Page> {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  if (offline) await ctx.route('**/tile.openstreetmap.org/**', (r) => r.abort('internetdisconnected'))
  const page = await ctx.newPage()
  await page.goto('/login')
  await page.getByLabel('Username').fill('coordinator')
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: 'Sign in' }).click()
  await expect(page.getByRole('button', { name: 'Log out' }).first()).toBeVisible()
  return page
}

test('flood, selected vehicle, full screen, offline network, War Room, approved reroute', async ({ browser }) => {
  test.setTimeout(240_000)
  const p = await login(browser)
  const token = await p.evaluate(() => { const raw = sessionStorage.getItem('flowguard.session') ?? localStorage.getItem('flowguard.session') ?? ''; try { return JSON.parse(raw).token as string } catch { return '' } })
  const res = await p.request.post('/api/demo/use-cases/flood-reroute/setup', { headers: { Authorization: `Bearer ${token}` }, data: { mode: 'jump' } })
  expect(res.ok()).toBeTruthy()
  await p.reload()
  await expect(p.locator('.fg-dis').first()).toBeVisible({ timeout: 20_000 })
  await p.waitForTimeout(3500)
  await p.screenshot({ path: `${OUT}/20-flood-control-tower.png` })

  await p.getByTestId('priority-list').getByRole('button', { name: /PTH-1116-01/ }).click()
  await expect(p.getByTestId('vehicle-panel')).toBeVisible()
  await p.waitForTimeout(2500)
  await p.screenshot({ path: `${OUT}/21-selected-shipment.png` })

  await p.getByRole('button', { name: 'Full-screen map' }).click()
  await p.waitForTimeout(2500)
  await p.screenshot({ path: `${OUT}/22-fullscreen-map.png` })
  await p.keyboard.press('Escape')

  const off = await login(browser, true)
  await expect(off.getByTestId('map-offline-label')).toBeVisible({ timeout: 20_000 })
  await off.getByTestId('priority-list').getByRole('button', { name: /PTH-1116-01/ }).click()
  await off.waitForTimeout(1500)
  await off.screenshot({ path: `${OUT}/23-offline-network-map.png` })
  await off.context().close()

  await p.getByTestId('vehicle-panel').getByRole('button', { name: 'Open War Room' }).click()
  await p.getByRole('button', { name: 'Run scenarios' }).click()
  await expect(p.getByText('RECOMMENDED: REROUTE')).toBeVisible()
  await p.waitForTimeout(800)
  await p.screenshot({ path: `${OUT}/24-war-room.png`, fullPage: true })
  await p.getByRole('button', { name: 'Approve Reroute' }).click()
  await expect(p.getByText(/Reroute approved and applied/)).toBeVisible()

  await p.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Control Tower' }).click()
  await expect(p.locator('.fg-routelabel.active')).toHaveCount(1, { timeout: 15_000 })
  await p.waitForTimeout(3500)
  await p.screenshot({ path: `${OUT}/25-approved-reroute.png` })
})
