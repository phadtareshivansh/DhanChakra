import { test, expect } from '@playwright/test'
import { preparePage, type Theme } from './helpers'

const ENTITY = 'L12345MH2023PLC900002'

const screens = [
  { name: 'dashboard', path: '/', heading: 'Fraud intelligence' },
  { name: 'worklist', path: '/worklist', heading: 'Risk worklist' },
  { name: 'entity', path: `/entity/${ENTITY}/network`, heading: 'Maya Trading Co Pvt Ltd' },
  { name: 'graph', path: `/graph/${ENTITY}`, heading: 'Graph workspace' },
  { name: 'cases', path: '/cases', heading: 'Case files' },
] as const

for (const theme of ['light', 'dark'] as Theme[]) {
  test.describe(`${theme} theme`, () => {
    for (const screen of screens) {
      test(`${screen.name} visual snapshot`, async ({ page }) => {
        await preparePage(page, { theme, path: screen.path })
        await expect(page.getByRole('heading', { name: screen.heading }).first()).toBeVisible()
        if (screen.name === 'graph') {
          await expect(page.locator('svg[role="img"]')).toBeVisible()
        }
        await page.waitForTimeout(450)
        await expect(page).toHaveScreenshot(`${screen.name}-${theme}.png`, {
          fullPage: true,
          timeout: 20_000,
        })
      })
    }

    test('login visual snapshot', async ({ page }) => {
      await preparePage(page, { theme, path: '/login', authenticated: false })
      await expect(page.getByRole('heading', { name: 'Dhan-Chakra' })).toBeVisible()
      await expect(page).toHaveScreenshot(`login-${theme}.png`, { fullPage: true })
    })
  })
}

test.describe('phone layout', () => {
  test.use({ viewport: { width: 390, height: 844 }, colorScheme: 'light' })

  test('graph is a read-only table with a notice', async ({ page }) => {
    await preparePage(page, { theme: 'light', path: `/graph/${ENTITY}` })
    await expect(
      page.getByText('The interactive graph is available on tablet and desktop.', { exact: false }),
    ).toBeVisible()
    await expect(page.getByRole('region', { name: 'Graph table view' })).toBeVisible()
    await expect(page.locator('svg[role="img"]')).toHaveCount(0)
    await expect(page).toHaveScreenshot('graph-phone-light.png', { fullPage: true })
  })
})
