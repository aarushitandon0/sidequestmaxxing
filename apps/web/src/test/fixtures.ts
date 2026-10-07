import type { Quest } from '../lib/types'

export const QUEST: Quest = {
  id: 'q1',
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
  place: { id: 'way/1', name: 'Riverside Park', lat: 18.52, lng: 73.85 },
}
