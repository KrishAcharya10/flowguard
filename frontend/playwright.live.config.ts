import { defineConfig } from '@playwright/test'

// Checks the ALREADY RUNNING site on port 8000 (start it first). Read-only: it does not change any data.
export default defineConfig({
  testDir: './e2e-live',
  timeout: 90_000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8000' },
})
