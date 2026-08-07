import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Check, Plus, X, Target, Clock, Zap, ChevronLeft, ChevronRight } from 'lucide-react'

function isoWeek(offset = 0): string {
  const d = new Date()
  d.setDate(d.getDate() + offset * 7)
  const dayNum = d.getUTCDay() || 7
  d.setUTCDate(d.getUTCDate() + 4 - dayNum)
  const yearStart = new Date(Date.UTC(d.getUTCFullYear(), 0, 1))
  const weekNo = Math.ceil(((d.getTime() - yearStart.getTime()) / 86400000 + 1) / 7)
  return `${d.getUTCFullYear()}-W${String(weekNo).padStart(2, '0')}`
}

export default function WeeklyOverview() {
  const queryClient = useQueryClient()
  const [weekOffset, setWeekOffset] = useState(0)
  const week = isoWeek(weekOffset)

  const { data } = useQuery({
    queryKey: ['weekly', week],
    queryFn: () => api.weeklyOverview(week),
  })

  const [hoursTarget, setHoursTarget] = useState<number | null>(null)
  const [sessions, setSessions] = useState<Array<{ sport: string; label: string; done: boolean }>>([])
  const [newLabel, setNewLabel] = useState('')
  const [newSport, setNewSport] = useState('running')

  useEffect(() => {
    if (data) {
      setHoursTarget(data.hours_target)
      setSessions(data.quality_sessions?.length ? data.quality_sessions : [])
    }
  }, [data])

  const save = useMutation({
    mutationFn: () => api.updateWeeklyGoal({
      week,
      hours_target: hoursTarget ?? undefined,
      quality_sessions: sessions,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['weekly', week] }),
  })

  const toggleSession = (idx: number) => {
    const updated = [...sessions]
    updated[idx] = { ...updated[idx], done: !updated[idx].done }
    setSessions(updated)
    api.updateWeeklyGoal({ week, hours_target: hoursTarget ?? undefined, quality_sessions: updated })
      .then(() => queryClient.invalidateQueries({ queryKey: ['weekly', week] }))
  }

  const addSession = () => {
    if (!newLabel.trim()) return
    const updated = [...sessions, { sport: newSport, label: newLabel.trim(), done: false }]
    setSessions(updated)
    setNewLabel('')
    api.updateWeeklyGoal({ week, hours_target: hoursTarget ?? undefined, quality_sessions: updated })
      .then(() => queryClient.invalidateQueries({ queryKey: ['weekly', week] }))
  }

  const removeSession = (idx: number) => {
    const updated = sessions.filter((_, i) => i !== idx)
    setSessions(updated)
    api.updateWeeklyGoal({ week, hours_target: hoursTarget ?? undefined, quality_sessions: updated })
      .then(() => queryClient.invalidateQueries({ queryKey: ['weekly', week] }))
  }

  const hoursPct = hoursTarget && hoursTarget > 0
    ? Math.min(100, ((data?.hours_actual || 0) / hoursTarget) * 100)
    : 0
  const sessionsDone = sessions.filter((s) => s.done).length
  const sessionsTotal = sessions.length

  const sportColors: Record<string, string> = {
    running: 'bg-sport-running', cycling: 'bg-sport-cycling',
    swimming: 'bg-sport-swimming', strength: 'bg-sport-strength',
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Week Overview</h1>
        <div className="flex items-center gap-2">
          <button onClick={() => setWeekOffset((o) => o - 1)} className="p-1.5 rounded-lg bg-bg-secondary hover:bg-bg-hover">
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium min-w-[100px] text-center">
            {week}
          </span>
          <button onClick={() => setWeekOffset((o) => o + 1)} className="p-1.5 rounded-lg bg-bg-secondary hover:bg-bg-hover">
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {data && (
        <div className="text-xs text-slate-500">
          {data.week_start} — {data.week_end}
        </div>
      )}

      {/* Hours progress */}
      <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            <span className="text-sm font-medium">Hours</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold">{data?.hours_actual || 0}h</span>
            {hoursTarget && (
              <span className="text-sm text-slate-500">/ {hoursTarget}h</span>
            )}
          </div>
        </div>
        {hoursTarget && hoursTarget > 0 && (
          <div className="w-full bg-bg-tertiary rounded-full h-2.5">
            <div
              className="h-2.5 rounded-full transition-all bg-accent"
              style={{ width: `${hoursPct}%` }}
            />
          </div>
        )}
        <div className="mt-3 flex items-center gap-2">
          <label className="text-xs text-slate-500">Target:</label>
          <input
            type="number"
            value={hoursTarget ?? ''}
            onChange={(e) => setHoursTarget(e.target.value ? Number(e.target.value) : null)}
            onBlur={() => save.mutate()}
            placeholder="—"
            className="w-16 bg-bg-tertiary text-xs rounded px-2 py-1 border border-white/5 text-center"
          />
          <span className="text-xs text-slate-500">hours</span>
        </div>
      </div>

      {/* Sport breakdown */}
      {data?.by_sport && Object.keys(data.by_sport).length > 0 && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {Object.entries(data.by_sport).map(([sport, vals]: [string, any]) => (
            <div key={sport} className="bg-bg-secondary rounded-xl border border-white/5 p-3">
              <div className="flex items-center gap-2 mb-1">
                <div className={`w-2 h-2 rounded-full ${sportColors[sport] || 'bg-sport-other'}`} />
                <span className="text-xs text-slate-400 capitalize">{sport}</span>
              </div>
              <div className="text-lg font-bold">{vals.hours}h</div>
              <div className="text-[10px] text-slate-500">
                {vals.count} sessions · {vals.tss} TSS
                {vals.distance_km > 0 && ` · ${vals.distance_km} km`}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Quality sessions */}
      <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-accent" />
            <span className="text-sm font-medium">Quality Sessions</span>
          </div>
          {sessionsTotal > 0 && (
            <span className="text-xs text-slate-500">{sessionsDone}/{sessionsTotal} done</span>
          )}
        </div>

        <div className="space-y-2">
          {sessions.map((s, i) => (
            <div
              key={i}
              className={`flex items-center gap-3 p-2.5 rounded-lg transition-colors ${
                s.done ? 'bg-success/5' : 'bg-bg-tertiary'
              }`}
            >
              <button
                onClick={() => toggleSession(i)}
                className={`w-5 h-5 rounded border flex items-center justify-center transition-colors flex-shrink-0 ${
                  s.done
                    ? 'bg-success border-success text-white'
                    : 'border-slate-600 hover:border-slate-400'
                }`}
              >
                {s.done && <Check className="w-3 h-3" />}
              </button>
              <div className={`w-2 h-2 rounded-full flex-shrink-0 ${sportColors[s.sport] || 'bg-sport-other'}`} />
              <span className={`text-sm flex-1 ${s.done ? 'line-through text-slate-500' : ''}`}>
                {s.label}
              </span>
              <button
                onClick={() => removeSession(i)}
                className="text-slate-600 hover:text-slate-400 p-1"
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
        </div>

        <div className="flex gap-2 mt-3">
          <select
            value={newSport}
            onChange={(e) => setNewSport(e.target.value)}
            className="bg-bg-tertiary text-xs rounded-lg px-2 py-1.5 border border-white/5"
          >
            <option value="running">Running</option>
            <option value="cycling">Cycling</option>
            <option value="swimming">Swimming</option>
            <option value="strength">Strength</option>
            <option value="other">Other</option>
          </select>
          <input
            type="text"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && addSession()}
            placeholder="e.g. Tempo run, SS intervals..."
            className="flex-1 bg-bg-tertiary text-xs rounded-lg px-3 py-1.5 border border-white/5 placeholder:text-slate-600"
          />
          <button
            onClick={addSession}
            disabled={!newLabel.trim()}
            className="px-3 py-1.5 text-xs rounded-lg bg-accent text-bg-primary hover:bg-accent-hover transition-colors disabled:opacity-30 flex items-center gap-1"
          >
            <Plus className="w-3 h-3" /> Add
          </button>
        </div>
      </div>

      {/* Quick stats */}
      <div className="flex gap-3 text-xs text-slate-500">
        <div className="flex items-center gap-1">
          <Zap className="w-3 h-3" />
          {data?.total_tss || 0} TSS this week
        </div>
        <div>{data?.activity_count || 0} activities</div>
      </div>
    </div>
  )
}
