import { defineConfig, devices } from '@playwright/test'

// Uses the pre-installed Chromium (no `playwright install`). Runs against a production
// build made with the fake verifier; the API is mocked per test with page.route().
const CHROMIUM = process.env.PW_CHROMIUM_PATH ?? '/opt/pw-browsers/chromium'

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:4173',
    serviceWorkers: 'block', // so page.route() sees every API call
    launchOptions: { executablePath: CHROMIUM },
  },
  projects: [
    { name: 'mobile', use: { ...devices['Pixel 7'], launchOptions: { executablePath: CHROMIUM } } },
  ],
  webServer: {
    command:
      'VITE_E2E_FAKE_VERIFIER=1 VITE_API_BASE_URL=http://127.0.0.1:8765 npx vite build --outDir dist-e2e --emptyOutDir && npx vite preview --outDir dist-e2e --port 4173 --strictPort --host 127.0.0.1',
    url: 'http://127.0.0.1:4173',
    timeout: 120_000,
    reuseExistingServer: false,
  },
})
