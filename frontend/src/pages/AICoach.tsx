import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Brain, Play, Trash2, Loader2 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'

const SESSION_TYPES = [
  { value: 'endurance', label: 'Endurance', desc: 'Easy aerobic riding' },
  { value: 'sweetspot', label: 'Sweet Spot', desc: '86-95% FTP' },
  { value: 'threshold', label: 'Threshold', desc: 'FTP intervals' },
  { value: 'vo2max', label: 'VO2max', desc: 'High intensity intervals' },
  { value: 'tempo', label: 'Tempo', desc: '76-87% FTP' },
  { value: 'intervals', label: 'Mixed Intervals', desc: 'Varied intensity' },
  { value: 'sprint', label: 'Sprints', desc: 'Neuromuscular power' },
]

export default function AICoach() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [sport, setSport] = useState('cycling')
  const [sessionType, setSessionType] = useState('sweetspot')
  const [duration, setDuration] = useState(60)
  const [notes, setNotes] = useState('')

  const { data: workouts = [] } = useQuery({ queryKey: ['workouts'], queryFn: () => api.workouts() })

  const generate = useMutation({
    mutationFn: () => api.generateSession({
      sport,
      session_type: sessionType,
      duration_minutes: duration,
      notes: notes || undefined,
    }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workouts'] }),
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.deleteWorkout(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['workouts'] }),
  })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <Brain className="w-5 h-5 text-accent" /> AI Session Writer
      </h1>

      <div className="bg-bg-secondary rounded-xl border border-white/5 p-4 space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Sport</label>
            <select
              value={sport}
              onChange={(e) => setSport(e.target.value)}
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
            >
              <option value="cycling">Cycling</option>
              <option value="running">Running</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Session Type</label>
            <select
              value={sessionType}
              onChange={(e) => setSessionType(e.target.value)}
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
            >
              {SESSION_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Duration</label>
            <select
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
            >
              {[30, 45, 60, 75, 90, 120].map((d) => (
                <option key={d} value={d}>{d} min</option>
              ))}
            </select>
          </div>
          <div className="flex items-end">
            <button
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
              className="w-full bg-accent hover:bg-accent-hover text-bg-primary text-sm font-medium px-4 py-2 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              {generate.isPending ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Generating...</>
              ) : (
                'Generate Session'
              )}
            </button>
          </div>
        </div>
        <div>
          <label className="text-xs text-slate-400 block mb-1">Notes (optional)</label>
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="e.g. focus on high cadence, or include 30/30s"
            className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
          />
        </div>
        {generate.isError && (
          <p className="text-xs text-danger">
            Failed to generate. Check AI settings (Ollama running? API key set?).
          </p>
        )}
      </div>

      <div>
        <h2 className="text-sm font-medium text-slate-300 mb-3">Saved Workouts</h2>
        {workouts.length === 0 ? (
          <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
            No workouts yet. Generate one above or create manually.
          </div>
        ) : (
          <div className="space-y-2">
            {workouts.map((w: any) => (
              <WorkoutCard
                key={w.id}
                workout={w}
                onOpen={() => navigate(`/trainer?workout=${w.id}`)}
                onDelete={() => remove.mutate(w.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function WorkoutCard({ workout, onOpen, onDelete }: { workout: any; onOpen: () => void; onDelete: () => void }) {
  const totalMins = workout.duration_seconds ? Math.round(workout.duration_seconds / 60) : null

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4 hover:bg-bg-hover transition-colors">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <h3 className="font-medium text-sm">{workout.name}</h3>
          <p className="text-xs text-slate-400 mt-0.5">{workout.description}</p>
          <div className="flex gap-3 mt-2 text-xs text-slate-500">
            {workout.workout_type && (
              <span className="px-2 py-0.5 rounded bg-accent/10 text-accent capitalize">
                {(workout.workout_type || '').replace(/_/g, ' ')}
              </span>
            )}
            {totalMins && <span>{totalMins} min</span>}
            {workout.tss_estimate && <span>{Math.round(workout.tss_estimate)} TSS</span>}
            <span className="px-1.5 py-0.5 rounded bg-white/5">{workout.source}</span>
          </div>
        </div>
        <div className="flex gap-1 ml-2">
          <button
            onClick={onOpen}
            className="p-2 rounded-lg hover:bg-accent/20 text-accent transition-colors"
            title="Open in Trainer"
          >
            <Play className="w-4 h-4" />
          </button>
          <button
            onClick={onDelete}
            className="p-2 rounded-lg hover:bg-danger/20 text-slate-500 hover:text-danger transition-colors"
            title="Delete"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  )
}
