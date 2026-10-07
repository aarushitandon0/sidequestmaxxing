/** Types mirroring the API schemas (MASTERSPEC §6; apps/api/app/models). Keep in sync. */

export type Category =
  | 'explorer'
  | 'naturalist'
  | 'social'
  | 'foodie'
  | 'creative'
  | 'fitness'
  | 'mindful'
export type Mood = 'curious' | 'tired' | 'restless' | 'social' | 'calm' | 'adventurous'
export type Persona = 'chill' | 'dramatic' | 'nature_nerd' | 'sarcastic'
export type VerificationMethod = 'photo' | 'checkin' | 'honor'
export type Rarity = 'common' | 'rare' | 'legendary'
export type QuestStatus = 'offered' | 'accepted' | 'completed' | 'skipped' | 'expired'

export const CATEGORIES: readonly Category[] = [
  'explorer',
  'naturalist',
  'social',
  'foodie',
  'creative',
  'fitness',
  'mindful',
]
export const MOODS: readonly Mood[] = ['curious', 'calm', 'restless', 'adventurous', 'social', 'tired']
export const PERSONAS: readonly Persona[] = ['chill', 'dramatic', 'nature_nerd', 'sarcastic']

export interface PlaceRef {
  id: string
  name: string
  lat: number
  lng: number
}

export interface Quest {
  id: string
  title: string
  category: Category
  briefing: string
  objective: string
  place_id: string | null
  est_minutes: number
  verification: { method: VerificationMethod; photo_prompt: string | null }
  safety_note: string
  off_screen_tip: string
  rarity: Rarity
  xp: number
  distance_m: number | null
  place: PlaceRef | null
}

export interface QuestRequest {
  lat: number
  lng: number
  minutes_available: number
  radius_m: number
  mood: Mood
  interests: string[]
  persona: Persona
  mode: 'walk' | 'transit_ok'
  local_time_iso: string
}

export interface QuestState {
  id: string
  status: QuestStatus
  accepted_at: string | null
  expires_at: string
}

/** What the client sends after verifying. There is deliberately no image field. */
export interface VerificationResult {
  method: VerificationMethod
  match?: boolean | null
  confidence?: number | null
  seen?: string | null
}

export interface CompletionRequest {
  verification: VerificationResult
  elapsed_seconds: number
  screen_seconds: number
  checkin?: { lat: number; lng: number }
  note?: string
}

export interface LevelUp {
  kind: 'category' | 'overall'
  category: Category | null
  from_level: number
  to_level: number
  title: string | null
}

export interface CompletionResult {
  quest_id: string
  xp_awarded: number
  level_ups: LevelUp[]
  streak: number
  total_xp: number
  level: number
  within_radius: boolean | null
  screen_share: number | null
  daily_cap_reached: boolean
}

export interface SkillProgress {
  xp: number
  level: number
  title: string | null
  next_level_xp: number
}

export interface RecentCompletion {
  quest_id: string
  completed_at: string
  title: string | null
  category: Category
  xp_awarded: number
  verification_method: VerificationMethod
  place_name: string | null
  minutes_outside: number
  screen_share: number | null
}

export interface Profile {
  persona: Persona
  interests: string[]
  default_radius_m: number
  skills: Record<Category, SkillProgress>
  total_xp: number
  level: number
  next_level_xp: number
  streak_days: number
  quests_completed: number
  settings: { safe_mode: boolean; voice: boolean }
  recent: RecentCompletion[]
}

export interface SettingsUpdate {
  persona?: Persona
  interests?: string[]
  default_radius_m?: number
  voice?: boolean
  safe_mode?: boolean
}

export type ServiceState = 'ok' | 'down' | 'unknown'
export interface Health {
  status: 'ok'
  db: ServiceState
  llm: ServiceState
}
