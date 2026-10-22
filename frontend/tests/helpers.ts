import { readFileSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import type { Page, Route } from '@playwright/test'

const testsDir = dirname(fileURLToPath(import.meta.url))
const fixture = (name: string) =>
  JSON.parse(readFileSync(join(testsDir, 'fixtures', `${name}.json`), 'utf8'))

export type Theme = 'light' | 'dark'

const entity = fixture('entity')

/**
 * The visual suite runs without a backend. Fixtures are captured from the demo
 * tenant so the screenshots exercise realistic counts, names and risk bands.
 */
export async function mockApi(page: Page) {
  await page.route('**/api/v1/**', async (route: Route) => {
    const request = route.request()
    if (request.method() === 'OPTIONS') {
      return route.fulfill({ status: 204 })
    }
    const path = new URL(request.url()).pathname.replace('/api/v1', '')

    if (path === '/notifications') return route.fulfill({ json: fixture('notifications') })
    if (path === '/stats/overview') return route.fulfill({ json: fixture('stats') })
    if (path === '/analytics/loops') return route.fulfill({ json: fixture('loops') })
    if (path === '/audit') return route.fulfill({ json: fixture('audit') })
    if (path === '/worklist') return route.fulfill({ json: fixture('worklist') })
    if (path === '/worklist/facets') return route.fulfill({ json: fixture('facets') })
    if (path === '/worklist/assignments') return route.fulfill({ json: fixture('assignments') })
    if (path === '/users/assignable') return route.fulfill({ json: fixture('users') })
    if (path === '/cases') return route.fulfill({ json: fixture('cases') })

    if (/^\/entities\/[^/]+\/network\/timeline$/.test(path)) {
      return route.fulfill({ json: fixture('timeline') })
    }
    if (/^\/entities\/[^/]+\/network$/.test(path)) {
      return route.fulfill({ json: fixture('network') })
    }
    if (/^\/entities\/[^/]+\/explain$/.test(path)) {
      return route.fulfill({ json: fixture('explain') })
    }
    if (/^\/entities\/[^/]+\/history$/.test(path)) {
      return route.fulfill({ json: fixture('history') })
    }
    if (/^\/entities\/[^/]+\/notes$/.test(path)) {
      return route.fulfill({ json: fixture('notes') })
    }
    if (/^\/entities\/[^/]+\/timeline$/.test(path)) {
      return route.fulfill({ json: { timeline: [] } })
    }
    if (/^\/entities\/[^/]+$/.test(path)) {
      return route.fulfill({ json: entity })
    }

    // Keep unexpected calls visible without hanging the page.
    console.warn(`visual fixture missing for ${request.method()} ${path}`)
    return route.fulfill({ json: {} })
  })
}

export async function preparePage(
  page: Page,
  options: {
    theme: Theme
    path: string
    authenticated?: boolean
    /** Use 'persist' when the test switches language and the page reloads. */
    language?: 'en' | 'hi' | 'persist'
  },
) {
  await page.addInitScript(
    ({ theme, authenticated, language }) => {
      localStorage.setItem('dhanchakra_theme', theme)
      if (language !== 'persist') localStorage.setItem('dhanchakra_language', language ?? 'en')
      if (authenticated) {
        localStorage.setItem('dhanchakra_token', 'visual-test-token')
        localStorage.setItem('dhanchakra_refresh_token', 'visual-test-refresh')
        localStorage.setItem(
          'dhanchakra_user',
          JSON.stringify({
            id: 'visual-user',
            email: 'analyst@dggi.gov.in',
            display_name: 'Analyst Sharma',
            role: 'admin',
          }),
        )
      }
    },
    {
      theme: options.theme,
      authenticated: options.authenticated ?? true,
      language: options.language ?? 'en',
    },
  )
  // Web fonts are external; block them so Linux screenshots do not depend on
  // Google Fonts latency or a runner's network policy.
  await page.route('https://fonts.googleapis.com/**', (route) => route.abort())
  await page.route('https://fonts.gstatic.com/**', (route) => route.abort())
  await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: options.theme })
  await mockApi(page)
  await page.goto(options.path)
  await page.waitForLoadState('networkidle')
}
