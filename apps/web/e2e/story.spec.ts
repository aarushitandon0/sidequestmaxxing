import { expect, test } from '@playwright/test'

const SCENES = ['hero', 'problem', 'dm', 'walk', 'verified', 'skills', 'open', 'try']

test('every story scene is reachable by scrolling', async ({ page }) => {
  await page.goto('/')
  for (const id of SCENES) {
    const scene = page.locator(`[data-scene="${id}"]`)
    await scene.scrollIntoViewIfNeeded()
    await expect(scene.getByRole('heading').first()).toBeVisible()
  }
  // Receipts is hidden until evals/ has results.
  await expect(page.locator('[data-scene="receipts"]')).toHaveCount(0)
})

test('scroll drives --progress on a scene', async ({ page }) => {
  await page.goto('/')
  const walk = page.locator('[data-scene="walk"]')
  await walk.evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY + 10))
  await page.waitForTimeout(150)
  const early = Number(await walk.evaluate((el) => getComputedStyle(el).getPropertyValue('--progress')))
  await walk.evaluate((el) => window.scrollTo(0, el.getBoundingClientRect().bottom + window.scrollY - window.innerHeight - 5))
  await page.waitForTimeout(150)
  const late = Number(await walk.evaluate((el) => getComputedStyle(el).getPropertyValue('--progress')))
  expect(early).toBeLessThan(0.2)
  expect(late).toBeGreaterThan(0.9)
})

test('reduced motion renders every scene statically with final states', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  for (const id of SCENES.filter((s) => s !== 'hero')) {
    const scene = page.locator(`[data-scene="${id}"]`)
    const [position, progress] = await scene.evaluate((el) => [
      getComputedStyle(el.querySelector('.scene-stage')!).position,
      getComputedStyle(el).getPropertyValue('--progress').trim(),
    ])
    expect(position).toBe('static')
    expect(progress).toBe('1')
  }
})
