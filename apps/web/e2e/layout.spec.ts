import { expect, test } from '@playwright/test'

import { mockApi } from './mockApi'

// The layout must use the space on wide screens without ever scrolling sideways on phones.
const PAGES = ['/', '/onboarding?fresh', '/home', '/map', '/profile', '/chronicle', '/settings']

for (const width of [360, 390, 768, 1024, 1440]) {
  test.describe(`${width}px`, () => {
    test.use({ viewport: { width, height: 900 } })
    test('no horizontal page scroll', async ({ page }) => {
      await mockApi(page)
      await page.addInitScript(() => {
        if (location.search.includes('fresh')) return
        localStorage.setItem('sqm.prefs.v1', JSON.stringify({ persona: 'chill', interests: [], radiusM: 2500, voice: true,
          safetyAck: true, onboarded: true, minutes: 45, mood: 'curious' }))
      })
      for (const path of PAGES) {
        await page.goto(path)
        await page.waitForLoadState('networkidle')
        const { scroll, client } = await page.evaluate(() => ({
          scroll: document.documentElement.scrollWidth,
          client: document.documentElement.clientWidth,
        }))
        expect(scroll, `${path} at ${width}px`).toBeLessThanOrEqual(client)
      }
    })
  })
}
