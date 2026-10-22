/**
 * Lightweight i18n for Dhan-Chakra.
 *
 * Product copy is addressed by its English source string, so a missing
 * translation degrades gracefully to readable English rather than a key.
 * The Hindi dictionary lives in `hi.ts`; `check-hi.mjs` fails the build if a
 * used key has no translation.
 *
 * Language changes reload the document. That keeps every synchronous string
 * (including module-level labels and error copy) in the selected language
 * without threading a context through every component.
 */

import { HI } from './hi'

export type Language = 'en' | 'hi'

const LANGUAGE_KEY = 'dhanchakra_language'

export function getLanguage(): Language {
  try {
    const stored = localStorage.getItem(LANGUAGE_KEY)
    if (stored === 'en' || stored === 'hi') return stored
    return navigator.language?.toLowerCase().startsWith('hi') ? 'hi' : 'en'
  } catch {
    return 'en'
  }
}

const language = getLanguage()

if (typeof document !== 'undefined') {
  document.documentElement.lang = language === 'hi' ? 'hi' : 'en'
}

/** Switch language and reload so every module re-reads the dictionary. */
export function setLanguage(next: Language) {
  try {
    localStorage.setItem(LANGUAGE_KEY, next)
  } catch {
    // Storage may be unavailable in private contexts; the reload still works.
  }
  window.location.reload()
}

/**
 * Translate a source string. `{name}` placeholders are replaced from `values`.
 * Unknown Hindi keys fall back to English instead of showing a raw key.
 */
export function t(source: string, values?: Record<string, string | number>): string {
  const translated = language === 'hi' ? HI[source] ?? source : source
  if (!values) return translated
  return translated.replace(/\{(\w+)\}/g, (match, key: string) => {
    const value = values[key]
    return value === undefined ? match : String(value)
  })
}

export function currentLanguage(): Language {
  return language
}
