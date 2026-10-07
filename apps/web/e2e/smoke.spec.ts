import { expect, test } from '@playwright/test'

import { mockApi, QUEST } from './mockApi'

test('onboarding → generate → accept → walk → back → verify on device → reward', async ({ page }) => {
  const requests = await mockApi(page)

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Sidequestmaxxing' })).toBeVisible()
  await page.getByRole('link', { name: /start your first quest/i }).first().click()

  // Onboarding: 3 taps.
  await page.getByRole('radio', { name: /chill/i }).click()
  await page.getByRole('button', { name: /continue/i }).click()
  await page.getByRole('button', { name: /i'll tell someone/i }).click()
  await expect(page).toHaveURL(/\/home$/)

  // Generate (demo area: no location permission needed).
  await page.getByRole('button', { name: /get a quest/i }).click()
  await page.getByRole('button', { name: /play in the demo area/i }).click()
  await expect(page.getByRole('heading', { name: QUEST.title })).toBeVisible()
  await expect(page.getByText(QUEST.safety_note)).toBeVisible()

  // Accept → Walk Mode with a running timer computed from accepted_at.
  await page.getByRole('button', { name: /accept quest/i }).click()
  await expect(page).toHaveURL(/\/walk$/)
  await expect(page.getByRole('heading', { name: /walk mode/i })).toBeVisible()
  await expect(page.getByRole('region', { name: 'Quest timer' })).toContainText(/16:0\d/)

  // Walk Mode survives a reload (state persisted locally).
  await page.reload()
  await expect(page.getByRole('heading', { name: /walk mode/i })).toBeVisible()

  // I'm back → Verify: one photo, checked on the device (fake verifier in e2e builds).
  await page.getByRole('button', { name: /i'm back/i }).click()
  await expect(page).toHaveURL(/\/verify$/)
  await page.getByLabel(/take a photo/i).setInputFiles({
    name: 'marker.jpg', mimeType: 'image/jpeg', buffer: Buffer.from([0xff, 0xd8, 0xff, 0xe0, 1, 2, 3, 4]),
  })
  await expect(page.getByText(/match found/i)).toBeVisible()
  await page.getByRole('button', { name: /claim reward/i }).click()

  await expect(page.getByRole('heading', { name: /quest complete/i })).toBeVisible()
  await expect(page.getByText(/your screen was on for 3% of this quest/i)).toBeVisible()

  // Privacy: no request ever carried image bytes; complete carried only the verdict.
  for (const r of requests) {
    const body = r.postData() ?? ''
    expect(body).not.toMatch(/data:image|base64|blob:/i)
    expect(r.headers()['content-type'] ?? 'application/json').not.toMatch(/multipart|image\//)
  }
  const complete = requests.find((r) => r.url().endsWith('/complete'))!
  const sent = JSON.parse(complete.postData()!)
  expect(Object.keys(sent).sort()).toEqual(['elapsed_seconds', 'screen_seconds', 'verification'])
  expect(sent.verification).toMatchObject({ method: 'photo', match: true })
})

test('LLM-down fallback is invisible to the player (any valid quest renders)', async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => {
    localStorage.setItem('sqm.prefs.v1', JSON.stringify({ onboarded: true, safetyAck: true }))
    localStorage.setItem('sqm.location_choice', JSON.stringify('demo'))
  })
  await page.goto('/home')
  await page.getByRole('button', { name: /get a quest/i }).click()
  await expect(page.getByRole('button', { name: /accept quest/i })).toBeVisible()
})
