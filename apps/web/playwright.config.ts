import { existsSync } from 'node:fs'

import { defineConfig, devices } from '@playwright/test'

// Prefers a pre-installed Chromium (no `playwright install`) and falls back to the one Playwright
// manages when that path is absent — the container has the former, a dev laptop the latter. Runs
// against a production build made with the fake verifier; the API is mocked per test page.route().
const CONFIGURED = process.env.PW_CHROMIUM_PATH ?? '/opt/pw-browsers/chromium'
const CHROMIUM = existsSync(CONFIGURED) ? CONFIGURED : undefined
const launchOptions = { executablePath: CHROMIUM }

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    serviceWorkers: 'block', // so page.route() sees every API call
    launchOptions,
  },
  projects: [
    { name: 'mobile', use: { ...devices['Pixel 7'], launchOptions } },
  ],
  webServer: {
    // `env` rather than an inline `VAR=x cmd` prefix, which cmd.exe cannot parse on Windows.
    command:
      'npx vite build --outDir dist-e2e --emptyOutDir && npx vite preview --outDir dist-e2e --port 4173 --strictPort --host 127.0.0.1',
    env: {
      VITE_E2E_FAKE_VERIFIER: '1',
      VITE_API_BASE_URL: 'http://127.0.0.1:8765',
    },
    url: 'http://127.0.0.1:4173',
    timeout: 120_000,
    reuseExistingServer: false,
  },
})
