// Render docs/architecture.mmd to docs/architecture.svg OFFLINE, using the locally installed Mermaid
// package and Playwright's Chromium. Run from frontend/:  node ../scripts/render_diagram.mjs
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const require = createRequire(join(process.cwd(), 'package.json'))
const { chromium } = require('@playwright/test')
const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const source = readFileSync(join(root, 'docs', 'architecture.mmd'), 'utf8')
const mermaidJs = readFileSync(require.resolve('mermaid/dist/mermaid.min.js'), 'utf8')

const browser = await chromium.launch()
const page = await browser.newPage()
await page.setContent('<html><body></body></html>')
await page.addScriptTag({ content: mermaidJs })
const svg = await page.evaluate(async (def) => {
  window.mermaid.initialize({ startOnLoad: false, theme: 'neutral', flowchart: { htmlLabels: false, wrappingWidth: 260 } })
  const { svg } = await window.mermaid.render('architecture', def)
  return svg
}, source)
await browser.close()
writeFileSync(join(root, 'docs', 'architecture.svg'), svg)
console.log('wrote docs/architecture.svg', svg.length, 'bytes')
