import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { preparePage, type Theme } from './helpers'

const ENTITY = 'L12345MH2023PLC900002'

const pagesAxe = [
  { name: 'dashboard', path: '/', heading: 'Fraud intelligence' },
  { name: 'worklist', path: '/worklist', heading: 'Risk worklist' },
  { name: 'entity', path: `/entity/${ENTITY}/network`, heading: 'Maya Trading Co Pvt Ltd' },
  { name: 'graph', path: `/graph/${ENTITY}`, heading: 'Graph workspace' },
  { name: 'cases', path: '/cases', heading: 'Case files' },
  { name: 'settings', path: '/settings', heading: 'Settings' },
] as const

for (const theme of ['light', 'dark'] as Theme[]) {
  test.describe(`axe ${theme}`, () => {
    for (const entry of pagesAxe) {
      test(`${entry.name} has no WCAG 2.2 A/AA violations`, async ({ page }) => {
        await preparePage(page, { theme, path: entry.path })
        await expect(page.getByRole('heading', { name: entry.heading }).first()).toBeVisible()
        await page.waitForTimeout(300)
        const results = await new AxeBuilder({ page })
          .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
          .analyze()
        const summary = results.violations.map((violation) => ({
          id: violation.id,
          impact: violation.impact,
          help: violation.help,
          targets: violation.nodes.map((node) => node.target.join(' ')),
        }))
        expect(summary, JSON.stringify(summary, null, 2)).toEqual([])
      })
    }

    test('login has no WCAG 2.2 A/AA violations', async ({ page }) => {
      await preparePage(page, { theme, path: '/login', authenticated: false })
      await expect(page.getByRole('heading', { name: 'Dhan-Chakra' })).toBeVisible()
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'])
        .analyze()
      const summary = results.violations.map((violation) => ({
        id: violation.id,
        impact: violation.impact,
        help: violation.help,
        targets: violation.nodes.map((node) => node.target.join(' ')),
      }))
      expect(summary, JSON.stringify(summary, null, 2)).toEqual([])
    })
  })
}
