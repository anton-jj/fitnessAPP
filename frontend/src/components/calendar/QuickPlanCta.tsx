import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../../api/client'
import { UserCog, Zap, Loader2 } from 'lucide-react'

/** Shown above the calendar when there is no active plan: the onboarding
 *  entry point, plus a one-off "quick plan" generator for anyone who wants a
 *  week of structure without doing the full setup. Lifted verbatim (data and
 *  behavior) from the old Plan.tsx `!hasPlan` block. */
export default function QuickPlanCta() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [sports, setSports] = useState(['cycling', 'running'])
  const [hours, setHours] = useState(8)
  const [notes, setNotes] = useState('')

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.profile(),
  })

  const generate = useMutation({
    mutationFn: () => api.generatePlan({ sports, hours, notes: notes || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan'] })
    },
  })

  return (
    <div className="space-y-4">
      <div className="bg-bg-secondary rounded-xl border border-accent/20 p-5 space-y-3">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-xl bg-accent/10">
            <UserCog className="w-5 h-5 text-accent" />
          </div>
          <div className="flex-1">
            <h2 className="text-sm font-semibold">Structured Training</h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Complete the onboarding wizard to set up your athlete profile — goals, weaknesses,
              schedule, equipment. The AI builds a multi-week periodized plan with daily workouts
              automatically pushed to your watch.
            </p>
          </div>
        </div>
        <button
          onClick={() => navigate('/onboarding')}
          className="bg-accent hover:bg-accent-hover text-bg-primary text-sm font-medium px-5 py-2.5 rounded-lg transition-colors flex items-center gap-2"
        >
          <Zap className="w-4 h-4" />
          {profile?.onboarding_complete ? 'Update Profile & Regenerate' : 'Start Onboarding'}
        </button>
      </div>

      <div className="bg-bg-secondary rounded-xl border border-white/5 p-5 space-y-4">
        <h2 className="text-sm font-semibold">Quick Weekly Plan</h2>
        <p className="text-xs text-slate-400">
          Generate a one-off weekly plan without the full setup.
        </p>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Sports</label>
            <div className="flex flex-wrap gap-1.5">
              {['cycling', 'running', 'swimming', 'strength'].map((s) => (
                <button
                  key={s}
                  onClick={() =>
                    setSports((prev) =>
                      prev.includes(s) ? prev.filter((x) => x !== s) : [...prev, s]
                    )
                  }
                  className={`px-2.5 py-1 text-xs rounded-lg transition-colors ${
                    sports.includes(s)
                      ? 'bg-accent/20 text-accent'
                      : 'bg-bg-tertiary text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Weekly Hours</label>
            <input
              type="number"
              value={hours}
              onChange={(e) => setHours(Number(e.target.value))}
              min={2}
              max={25}
              step={0.5}
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
            />
          </div>
          <div className="col-span-2">
            <label className="text-xs text-slate-400 block mb-1">Notes</label>
            <input
              type="text"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g. race on Sunday, easy week, focus on threshold"
              className="w-full bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
            />
          </div>
        </div>

        <button
          onClick={() => generate.mutate()}
          disabled={generate.isPending || sports.length === 0}
          className="bg-bg-tertiary hover:bg-bg-hover text-slate-300 text-sm font-medium px-5 py-2.5 rounded-lg transition-colors disabled:opacity-50 flex items-center gap-2"
        >
          {generate.isPending ? (
            <><Loader2 className="w-4 h-4 animate-spin" /> Generating — this takes a minute or two...</>
          ) : (
            'Generate Quick Plan'
          )}
        </button>

        {generate.isError && (
          <p className="text-xs text-danger">
            {(generate.error as Error).message}
          </p>
        )}
      </div>
    </div>
  )
}
