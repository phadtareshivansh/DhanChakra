import { test, expect } from '@playwright/test'
import { preparePage } from './helpers'

const ENTITY = 'L12345MH2023PLC900002'

test.describe('tablet layout', () => {
  test.use({ viewport: { width: 820, height: 1180 } })

  test('keeps the sidebar available without horizontal overflow', async ({ page }) => {
    await preparePage(page, { theme: 'light', path: '/' })
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Fraud intelligence' })).toBeVisible()
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
  })

  test('keeps the interactive graph available', async ({ page }) => {
    await preparePage(page, { theme: 'light', path: `/graph/${ENTITY}` })
    await expect(page.getByRole('heading', { name: 'Graph workspace' })).toBeVisible()
    await expect(page.locator('svg[role="img"]')).toBeVisible()
    await expect(page.getByRole('group', { name: 'View mode' }).getByRole('button', { name: 'Table' })).toBeVisible()
  })
})

test.describe('phone layout', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('uses the navigation drawer and has no horizontal overflow', async ({ page }) => {
    await preparePage(page, { theme: 'light', path: '/' })
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeHidden()
    await page.getByRole('button', { name: 'Open navigation' }).click()
    await expect(page.getByRole('navigation', { name: 'Primary navigation' })).toBeVisible()
    await page.getByRole('link', { name: 'Worklist', exact: true }).click()
    await expect(page.getByRole('heading', { name: 'Risk worklist' })).toBeVisible()
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true)
  })
})
