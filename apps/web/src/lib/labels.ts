import type { Category, Mood, Persona, Rarity, VerificationMethod } from './types'

/** RPG skill names shown in the UI for the 7 server categories (MASTERSPEC §6.2). */
export const SKILL_LABEL: Record<Category, string> = {
  explorer: 'Navigation',
  naturalist: 'Nature Lore',
  social: 'Fellowship',
  foodie: 'Taste Lore',
  creative: 'Creativity',
  fitness: 'Endurance',
  mindful: 'Observation',
}

export const CATEGORY_LABEL: Record<Category, string> = {
  explorer: 'Explorer',
  naturalist: 'Nature',
  social: 'Social',
  foodie: 'Foodie',
  creative: 'Creative',
  fitness: 'Fitness',
  mindful: 'Mindful',
}

export interface PersonaInfo {
  name: string
  blurb: string
}

export const PERSONA_INFO: Record<Persona, PersonaInfo> = {
  chill: { name: 'Chill', blurb: 'Calm, friendly, a bit funny.' },
  dramatic: { name: 'Dramatic', blurb: 'Over-the-top fantasy narrator.' },
  nature_nerd: { name: 'Nature Nerd', blurb: 'Delighted by trees, birds, geology facts.' },
  sarcastic: { name: 'Sarcastic', blurb: 'Dry humour, never mean.' },
}

export const MOOD_LABEL: Record<Mood, string> = {
  curious: 'Curious',
  calm: 'Calm',
  restless: 'Restless',
  adventurous: 'Adventurous',
  social: 'Social',
  tired: 'Tired',
}

export const RARITY_LABEL: Record<Rarity, string> = {
  common: 'Common',
  rare: 'Rare',
  legendary: 'Legendary',
}

export const METHOD_LABEL: Record<VerificationMethod, string> = {
  photo: 'Photo check',
  checkin: 'Check-in',
  honor: 'Honor mode',
}

/** Persona-flavoured greeting for the Dungeon Master bubble (pure UI copy). */
export function greeting(persona: Persona, hour: number): string {
  const part = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'
  switch (persona) {
    case 'dramatic':
      return `Good ${part}, brave adventurer! The realm stirs. A quest awaits your boots.`
    case 'nature_nerd':
      return `Good ${part}! Did you know your street is an ecosystem? Let's go and look at it.`
    case 'sarcastic':
      return `Oh, good ${part}. Still indoors? Bold. I've got something better for you.`
    default:
      return `Good ${part}, explorer! I've got a little something for you today.`
  }
}

export function formatDistance(m: number | null): string | null {
  if (m == null) return null
  return m < 1000 ? `${Math.round(m / 10) * 10} m` : `${(m / 1000).toFixed(1)} km`
}

export function formatMinutes(total: number): string {
  if (total < 60) return `${total} min`
  const h = Math.floor(total / 60)
  const m = total % 60
  return m ? `${h}h ${m}m` : `${h}h`
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = s % 60
  const mm = String(m).padStart(h ? 2 : 1, '0')
  const ss = String(sec).padStart(2, '0')
  return h ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
}
