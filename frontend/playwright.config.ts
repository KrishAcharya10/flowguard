import { defineConfig } from '@playwright/test'

// End-to-end test against the PRODUCTION build served by FastAPI (same origin, one worker).
export default defineConfig({
  testDir: './e2e',
  timeout: 90_000,
  workers: 1,
  reporter: 'list',
  use: { baseURL: 'http://127.0.0.1:8010', viewport: { width: 1400, height: 900 } },
  webServer: {
    command: '.venv\\Scripts\\python -m uvicorn app.main:app --port 8010 --workers 1',
    cwd: '../backend',
    url: 'http://127.0.0.1:8010/health',
    reuseExistingServer: false,
    timeout: 60_000,
    env: { FLOWGUARD_DB: 'sqlite:///./e2e.db', DEMO_MODE: 'true', FLOWGUARD_DOC_DIR: './storage-e2e/documents' },
  },
})
