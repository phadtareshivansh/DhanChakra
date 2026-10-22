import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = fileURLToPath(new URL('../src/', import.meta.url))
const used = new Set()

function walk(dir) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) {
      walk(full)
      continue
    }
    if (!full.endsWith('.tsx')) continue
    const source = readFileSync(full, 'utf8')
    const pattern = /\bt\('((?:[^'\\]|\\.)*)'/g
    for (const match of source.matchAll(pattern)) {
      used.add(match[1].replace(/\\'/g, "'").replace(/\\\\/g, '\\'))
    }
  }
}

walk(root)
const dictionary = readFileSync(join(root, 'i18n/hi.ts'), 'utf8')
const translated = new Set()
for (const match of dictionary.matchAll(/^  "((?:[^"\\]|\\.)*)":/gm)) {
  translated.add(match[1].replace(/\\"/g, '"').replace(/\\\\/g, '\\'))
}

const missing = [...used].filter((key) => !translated.has(key)).sort()
if (missing.length > 0) {
  console.error(`Missing ${missing.length} Hindi translation(s):`)
  for (const key of missing) console.error(`  - ${key}`)
  process.exit(1)
}
console.log(`i18n: ${used.size} strings, ${translated.size} Hindi entries, no missing keys.`)
