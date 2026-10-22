import { test, expect } from '@playwright/test'
import { preparePage } from './helpers'

test.describe('Hindi language', () => {
  test('switches the shell and dashboard copy to Hindi and persists', async ({ page }) => {
    await preparePage(page, { theme: 'light', path: '/', language: 'persist' })

    await expect(page.getByRole('heading', { name: 'Fraud intelligence' })).toBeVisible()
    await page.getByRole('button', { name: 'हिं' }).click()
    await page.waitForLoadState('networkidle')

    await expect(page.locator('html')).toHaveAttribute('lang', 'hi')
    await expect(page.getByRole('heading', { name: 'धोखाधड़ी इंटेलिजेंस' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'डैशबोर्ड' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'हिं' })).toHaveAttribute('aria-pressed', 'true')
    expect(await page.evaluate(() => localStorage.getItem('dhanchakra_language'))).toBe('hi')
  })
})
