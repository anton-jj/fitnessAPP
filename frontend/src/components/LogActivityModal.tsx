import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { X, Loader2 } from 'lucide-react'

const SPORTS = [
  { value: 'swimming', label: 'Swimming', icon: '🏊' },
  { value: 'strength', label: 'Strength', icon: '🏋️' },
  { value: 'running', label: 'Running', icon: '🏃' },
  { value: 'cycling', label: 'Cycling', icon: '🚴' },
  { value: 'hiking', label: 'Hiking', icon: '🥾' },
  { value: 'yoga', label: 'Yoga', icon: '🧘' },
  { value: 'xcski', label: 'XC Ski', icon: '⛷️' },
  { value: 'rowing', label: 'Rowing', icon: '🚣' },
  { value: 'other', label: 'Other', icon: '💪' },
]

interface Props {
  open: boolean
  onClose: () => void
}

export default function LogActivityModal({ open, onClose }: Props) {
  const queryClient = useQueryClient()
  const [sport, setSport] = useState('swimming')
  const [minutes, setMinutes] = useState(30)
  const [name, setName] = useState('')
  const [distance, setDistance] = useState('')
  const [notes, setNotes] = useState('')

  const log = useMutation({
    mutationFn: () => api.logActivity({
      sport_type: sport,
      name: name || undefined,
      duration_minutes: minutes,
      distance_km: distance ? Number(distance) : undefined,
      notes: notes || undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['activities'] })
      queryClient.invalidateQueries({ queryKey: ['dashboard'] })
      queryClient.invalidateQueries({ queryKey: ['weekly'] })
      setName('')
      setDistance('')
      setNotes('')
      onClose()
    },
  })

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div className="bg-bg-secondary rounded-2xl border border-white/10 p-5 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-bold">Log Activity</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-bg-hover">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1.5">Sport</label>
            <div className="grid grid-cols-3 gap-1.5">
              {SPORTS.map((s) => (
                <button
                  key={s.value}
                  onClick={() => setSport(s.value)}
                  className={`flex items-center gap-1.5 px-2.5 py-2 rounded-lg text-xs transition-colors ${
                    sport === s.value
                      ? 'bg-accent/20 text-accent border border-accent/30'
                      : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
                  }`}
                >
                  <span>{s.icon}</span> {s.label}
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1">Duration (min)</label>
              <input
                type="number"
                value={minutes}
                onChange={(e) => setMinutes(Number(e.target.value))}
                className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1">Distance (km, optional)</label>
              <input
                type="number"
                step="0.1"
                value={distance}
                onChange={(e) => setDistance(e.target.value)}
                placeholder="—"
                className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Name (optional)</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Morning swim"
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
            />
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Notes (optional)</label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="How did it go?"
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
            />
          </div>

          <button
            onClick={() => log.mutate()}
            disabled={log.isPending || minutes <= 0}
            className="w-full bg-accent hover:bg-accent-hover text-bg-primary text-sm font-medium px-4 py-2.5 rounded-lg transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {log.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
            Log Activity
          </button>
        </div>
      </div>
    </div>
  )
}
