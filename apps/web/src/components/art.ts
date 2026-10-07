import dmChill from '../assets/art/dm-chill.webp'
import dmDramatic from '../assets/art/dm-dramatic.webp'
import dmNatureNerd from '../assets/art/dm-nature_nerd.webp'
import dmSarcastic from '../assets/art/dm-sarcastic.webp'
import heroScene from '../assets/art/hero-scene.webp'
import sceneForest from '../assets/art/scene-forest.webp'
import sceneMountains from '../assets/art/scene-mountains.webp'
import sceneReward from '../assets/art/scene-reward.webp'
import sceneRiver from '../assets/art/scene-river.webp'
import sceneVerify from '../assets/art/scene-verify.webp'
import story1 from '../assets/art/story-1.webp'
import story2 from '../assets/art/story-2.webp'
import story3 from '../assets/art/story-3.webp'
import story4 from '../assets/art/story-4.webp'
import story5 from '../assets/art/story-5.webp'
import type { Category, Persona } from '../lib/types'

/** Art cropped from the project's design template (see docs/DECISIONS.md D-45). */
export const PORTRAIT: Record<Persona, string> = {
  chill: dmChill,
  dramatic: dmDramatic,
  nature_nerd: dmNatureNerd,
  sarcastic: dmSarcastic,
}

export const ART = {
  heroScene,
  sceneForest,
  sceneMountains,
  sceneReward,
  sceneRiver,
  sceneVerify,
  story: [story1, story2, story3, story4, story5],
} as const

/** Decorative scene per category for quest cards and lists (alt="" — purely decorative). */
export const CATEGORY_ART: Record<Category, string> = {
  explorer: story2,
  naturalist: sceneRiver,
  social: story5,
  foodie: story1,
  creative: story4,
  fitness: sceneForest,
  mindful: sceneMountains,
}
