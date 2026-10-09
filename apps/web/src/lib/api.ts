import { getDeviceId } from './device'
import type {
  CompletionRequest,
  CompletionResult,
  Health,
  Profile,
  Quest,
  QuestRequest,
  QuestSource,
  QuestState,
  SettingsUpdate,
  WeeklyRecap,
} from './types'

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.status = status
    this.code = code
  }

  /** True when the request never reached the server (offline, DNS, CORS). */
  get isNetwork(): boolean {
    return this.status === 0
  }
}

/** The X-Quest-Source response header; exposed through CORS by the API (MASTERSPEC §6.1). */
export const QUEST_SOURCE_HEADER = 'X-Quest-Source'

const questSource = (res: Response): QuestSource | null => {
  const v = res.headers.get(QUEST_SOURCE_HEADER)
  return v === 'llm' || v === 'fallback' ? v : null
}

async function request<T>(path: string, init: RequestInit = {}, onResponse?: (res: Response) => void): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: {
        'Content-Type': 'application/json',
        'X-Device-Id': getDeviceId(),
        ...init.headers,
      },
    })
  } catch {
    throw new ApiError(0, 'network', "Can't reach the Dungeon Master. Check your connection.")
  }
  if (!res.ok) {
    let code = 'http_error'
    let message = `Request failed (${res.status})`
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } }
      code = body.error?.code ?? code
      message = body.error?.message ?? message
    } catch {
      // Non-JSON error body: keep the generic message.
    }
    throw new ApiError(res.status, code, message)
  }
  onResponse?.(res)
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

/**
 * The whole API surface. JSON only — there is intentionally no method that sends images
 * or files: photos are verified on the device and never leave it (MASTERSPEC §9.3).
 */
export const api = {
  health: () => request<Health>('/healthz'),
  generateQuest: async (body: QuestRequest): Promise<Quest> => {
    let source: QuestSource | null = null
    const quest = await request<Quest>(
      '/v1/quests/generate',
      { method: 'POST', body: JSON.stringify(body) },
      (res) => {
        source = questSource(res)
      },
    )
    return { ...quest, source }
  },
  acceptQuest: (id: string) => post<QuestState>(`/v1/quests/${encodeURIComponent(id)}/accept`),
  skipQuest: (id: string) => post<QuestState>(`/v1/quests/${encodeURIComponent(id)}/skip`),
  completeQuest: (id: string, body: CompletionRequest) =>
    post<CompletionResult>(`/v1/quests/${encodeURIComponent(id)}/complete`, body),
  profile: () => request<Profile>('/v1/profile'),
  updateSettings: (body: SettingsUpdate) =>
    request<Profile>('/v1/profile/settings', { method: 'PUT', body: JSON.stringify(body) }),
  deleteProfile: () => request<void>('/v1/profile', { method: 'DELETE' }),
  weeklyRecap: () => post<WeeklyRecap>('/v1/recap/weekly'),
} as const

export function friendlyError(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.isNetwork) return "You're offline or the realm is unreachable. Try again in a moment."
    if (err.status === 429) return 'Slow down, adventurer. Try again in a bit.'
    if (err.status >= 500) return 'The quest archive is resting right now. Try again soon.'
    return err.message
  }
  return 'Something went wrong. Try again.'
}
