import type { Page, Request } from '@playwright/test'

export const API = 'http://127.0.0.1:8765'

export const QUEST = {
  id: '6f1c2c1e-0000-4000-8000-000000000001',
  title: 'The Riverbank Riddle',
  category: 'naturalist',
  briefing: 'Find the old stone marker by the river and look for a leaf growing in the cracks.',
  objective: 'Find the stone marker by the river.',
  place_id: 'way/1',
  est_minutes: 15,
  verification: { method: 'photo', photo_prompt: 'an old stone marker' },
  safety_note: 'Stay on the path and away from the water edge.',
  off_screen_tip: 'Phone in pocket.',
  rarity: 'common',
  xp: 30,
  distance_m: 1200,
  place: { id: 'way/1', name: 'Riverside Park', lat: 18.521, lng: 73.857 },
}

const PROFILE = {
  persona: 'chill', interests: [], default_radius_m: 2500,
  skills: Object.fromEntries(['explorer', 'naturalist', 'social', 'foodie', 'creative', 'fitness', 'mindful']
    .map((c) => [c, { xp: 0, level: 0, title: null, next_level_xp: 40 }])),
  total_xp: 0, level: 0, next_level_xp: 120, streak_days: 0, quests_completed: 0,
  settings: { safe_mode: true, voice: true }, recent: [],
}

/** Mocks the whole API; returns every request the app made to it. */
export async function mockApi(page: Page): Promise<Request[]> {
  const seen: Request[] = []
  await page.route(`${API}/**`, async (route) => {
    const req = route.request()
    seen.push(req)
    const path = new URL(req.url()).pathname
    const json = (body: unknown, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body),
        headers: { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': '*' } })
    if (req.method() === 'OPTIONS') return json({})
    if (path === '/healthz') return json({ status: 'ok', db: 'ok', llm: 'ok' })
    if (path === '/v1/quests/generate') return json(QUEST)
    if (path.endsWith('/accept')) {
      return json({ id: QUEST.id, status: 'accepted', accepted_at: new Date(Date.now() - 16 * 60_000).toISOString(),
        expires_at: new Date(Date.now() + 3600_000).toISOString() })
    }
    if (path.endsWith('/skip')) return json({ id: QUEST.id, status: 'skipped', accepted_at: null, expires_at: new Date().toISOString() })
    if (path.endsWith('/complete')) {
      return json({ quest_id: QUEST.id, xp_awarded: 36, level_ups: [], streak: 1, total_xp: 36, level: 0,
        within_radius: null, screen_share: 0.03, daily_cap_reached: false })
    }
    if (path.startsWith('/v1/profile')) return json(PROFILE)
    return json({ error: { code: 'not_found', message: 'nope' } }, 404)
  })
  return seen
}
