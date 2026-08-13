const BASE = '/api'

/** Fired when the API rejects us — the session expired, or the app restarted
 *  with an ephemeral signing key. AuthGate listens and shows the PIN screen. */
export const UNAUTHORIZED_EVENT = 'pulse:unauthorized'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    // The login call reports its own failures; anything else getting a 401
    // means the session went away underneath us.
    if (res.status === 401 && !path.startsWith('/auth/login')) {
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    const text = await res.text()
    let detail = text
    try {
      detail = JSON.parse(text).detail ?? text
    } catch {
      // not JSON — fall back to the raw body
    }
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export const api = {
  dashboard: (days = 90) => request<any>(`/dashboard?days=${days}`),
  volume: (weeks = 12) => request<any[]>(`/dashboard/volume?weeks=${weeks}`),

  activities: (params?: { sport?: string; days?: number; limit?: number; offset?: number }) => {
    const q = new URLSearchParams()
    if (params?.sport) q.set('sport', params.sport)
    if (params?.days) q.set('days', String(params.days))
    if (params?.limit) q.set('limit', String(params.limit))
    if (params?.offset) q.set('offset', String(params.offset))
    return request<any[]>(`/activities?${q}`)
  },
  activity: (id: number) => request<any>(`/activities/${id}`),
  calendar: (year?: number, month?: number) => {
    const q = new URLSearchParams()
    if (year) q.set('year', String(year))
    if (month) q.set('month', String(month))
    return request<Record<string, any[]>>(`/activities/calendar?${q}`)
  },

  wellness: (days = 30) => request<any[]>(`/wellness?days=${days}`),

  syncStatus: () => request<any>('/sync/status'),
  triggerSync: (days = 90) => request<any>('/sync', { method: 'POST', body: JSON.stringify({ days }) }),

  stravaStatus: () => request<any>('/auth/strava/status'),
  intervalsStatus: () => request<any>('/auth/intervals/status'),
  saveIntervals: (apiKey: string, athleteId: string) =>
    request<any>(`/auth/intervals?api_key=${encodeURIComponent(apiKey)}&athlete_id=${encodeURIComponent(athleteId)}`, { method: 'POST' }),

  generateSession: (data: { sport: string; session_type: string; duration_minutes: number; notes?: string }) =>
    request<any>('/ai/session', { method: 'POST', body: JSON.stringify(data) }),
  workouts: () => request<any[]>('/ai/workouts'),
  workout: (id: number) => request<any>(`/ai/workouts/${id}`),
  createWorkout: (data: any) => request<any>('/ai/workouts', { method: 'POST', body: JSON.stringify(data) }),
  deleteWorkout: (id: number) => request<any>(`/ai/workouts/${id}`, { method: 'DELETE' }),

  logActivity: (data: { sport_type: string; name?: string; duration_minutes: number; distance_km?: number; notes?: string }) =>
    request<any>('/activities', { method: 'POST', body: JSON.stringify(data) }),

  weeklyOverview: (week?: string) => {
    const q = week ? `?week=${week}` : ''
    return request<any>(`/weekly${q}`)
  },
  updateWeeklyGoal: (data: { week: string; hours_target?: number; quality_sessions: any[] }) =>
    request<any>('/weekly', { method: 'PUT', body: JSON.stringify(data) }),

  saveTrainerRide: (data: any) => request<any>('/trainer/save', { method: 'POST', body: JSON.stringify(data) }),
  exportFit: async (data: any) => {
    const res = await fetch(`${BASE}/trainer/fit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    })
    if (!res.ok) throw new Error('FIT export failed')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `pulse_ride_${new Date().toISOString().slice(0, 16).replace(/[:-]/g, '')}.fit`
    a.click()
    URL.revokeObjectURL(url)
  },

  exportActivities: (fmt: 'csv' | 'json', days = 365) => {
    const a = document.createElement('a')
    a.href = `${BASE}/activities/export/${fmt}?days=${days}`
    a.download = `pulse_activities.${fmt}`
    a.click()
  },

  aiUsage: () => request<any>('/ai/usage'),

  generatePlan: (data: { sports: string[]; hours: number; notes?: string; week_start?: string }) =>
    request<any>('/ai/plan', { method: 'POST', body: JSON.stringify(data) }),
  currentPlan: (week?: string) => {
    const q = week ? `?week=${week}` : ''
    return request<any>(`/ai/plan${q}`)
  },
  adjustPlan: (planId: number, action: string, details: string) =>
    request<any>(`/ai/plan/${planId}/adjust`, {
      method: 'POST',
      body: JSON.stringify({ action, details }),
    }),
  updatePlan: (planId: number, data: any) =>
    request<any>(`/ai/plan/${planId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePlan: (planId: number) =>
    request<any>(`/ai/plan/${planId}`, { method: 'DELETE' }),

  moveWorkout: (data: { plan_id: number; week_number: number; from_day: string; from_index: number; to_day: string }) =>
    request<any>('/ai/plan/move-workout', { method: 'POST', body: JSON.stringify(data) }),

  pushToWatch: (workout: any, date: string) =>
    request<any>('/ai/push-to-watch', {
      method: 'POST',
      body: JSON.stringify({ workout, date }),
    }),
  pushPlan: (planId: number, weekNumber?: number) =>
    request<any>('/ai/push-plan', {
      method: 'POST',
      body: JSON.stringify({ plan_id: planId, week_number: weekNumber }),
    }),
  planCompliance: (planId: number) => request<any>(`/ai/plan/${planId}/compliance`),
  adaptPlan: (planId: number) =>
    request<any>(`/ai/plan/${planId}/adapt`, { method: 'POST' }),
  // The feed URL carries a key once a PIN is set, and only the server can
  // derive it — so this is fetched rather than built here.
  planCalendarUrl: (planId: number) =>
    request<{ url: string }>(`/ai/plan/${planId}/calendar-url`).then((r) => r.url),

  session: () => request<{ required: boolean; authenticated: boolean }>('/auth/session'),
  login: (pin: string) =>
    request<any>('/auth/login', { method: 'POST', body: JSON.stringify({ pin }) }),
  logout: () => request<any>('/auth/logout', { method: 'POST' }),

  // .fit workout file for direct import into Garmin Connect or the COROS app
  downloadWorkoutFile: async (workout: any, date: string) => {
    const res = await fetch(`${BASE}/ai/workout-file`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ workout, date }),
    })
    if (!res.ok) throw new Error('Could not build the workout file')
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${date}_${(workout.name || 'workout').replace(/[^a-z0-9]/gi, '_')}.fit`
    a.click()
    URL.revokeObjectURL(url)
  },

  profile: () => request<any>('/profile'),
  updateProfile: (data: any) => request<any>('/profile', { method: 'PUT', body: JSON.stringify(data) }),
  generateFullPlan: (start: 'this_week' | 'next_week' = 'next_week') =>
    request<any>('/profile/generate-plan', {
      method: 'POST',
      body: JSON.stringify({ start }),
    }),
  generatePlanStatus: () => request<any>('/profile/generate-plan/status'),

  // Generation runs as a background job on the server, so start it and poll
  // rather than holding a request open for several minutes.
  generateFullPlanAndWait: async (
    onTick?: (seconds: number) => void,
    start: 'this_week' | 'next_week' = 'next_week',
  ) => {
    await api.generateFullPlan(start)
    const startedAt = Date.now()
    while (true) {
      await new Promise((r) => setTimeout(r, 3000))
      const state = await api.generatePlanStatus()
      onTick?.(Math.round((Date.now() - startedAt) / 1000))
      if (state.status === 'done') return state
      if (state.status === 'error') throw new Error(state.error || 'Plan generation failed')
      if (Date.now() - startedAt > 15 * 60 * 1000) {
        throw new Error('Plan generation timed out after 15 minutes')
      }
    }
  },

  settings: () => request<any>('/settings'),
  updateSettings: (data: any) => request<any>('/settings', { method: 'PUT', body: JSON.stringify(data) }),
}
