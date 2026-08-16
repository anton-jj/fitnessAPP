import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { UseMutationResult } from '@tanstack/react-query'
import { api } from '../../api/client'
import { SPORT_ICONS, SPORT_ICON_FALLBACK, SPORT_BADGE_CLASS, SPORT_BADGE_FALLBACK } from '../../lib/sport'
import {
  SkipForward, ArrowLeftRight, Watch, ChevronDown, Download, Loader2,
} from 'lucide-react'

const PRIORITY_COLORS: Record<string, string> = {
  key: 'bg-accent/20 text-accent',
  supporting: 'bg-info/20 text-info',
  optional: 'bg-slate-500/20 text-slate-400',
}

const ARCHETYPE_COLORS: Record<string, string> = {
  quality: 'bg-accent/20 text-accent',
  long: 'bg-warning/20 text-warning',
  easy: 'bg-info/20 text-info',
  supporting: 'bg-slate-500/20 text-slate-400',
}

// Steps are measured in whatever unit the movement uses: reps for lifting,
// time for everything else.
function formatStep(step: any): string {
  if (step.reps) return `${step.reps} reps`
  const seconds = step.duration
  if (!seconds && seconds !== 0) return '—'
  return `${Math.floor(seconds / 60)}:${(seconds % 60).toString().padStart(2, '0')}`
}

function formatPace(secondsPer: number, sport: string): string {
  const mins = Math.floor(secondsPer / 60)
  const secs = Math.round(secondsPer % 60).toString().padStart(2, '0')
  return `${mins}:${secs}${sport === 'swimming' ? '/100m' : '/km'}`
}

interface PlannedDay {
  weekNumber: number
  dayName: string
  workouts: any[]
}

interface DayDetailPanelProps {
  date: string
  displayDate: string
  dayInfo: PlannedDay | null
  activities: any[]
  swapActive: boolean
  swapSourceIndex: number | null
  onToggleSwapSource: (index: number) => void
  onSwapTargetClick: (index: number) => void
  adjust: UseMutationResult<any, Error, { action: string; details: string; week_number?: number }>
  pushToWatch: UseMutationResult<any, Error, { workout: any; date: string }>
}

/** Expanded detail for a single selected calendar day: planned workouts (with
 *  the swap/skip/push/download actions) plus the real activities logged that
 *  day, refactored from the old Plan.tsx per-day day-loop body to take one
 *  day's data instead of looping over the whole week. */
export default function DayDetailPanel({
  date, displayDate, dayInfo, activities, swapActive, swapSourceIndex,
  onToggleSwapSource, onSwapTargetClick, adjust, pushToWatch,
}: DayDetailPanelProps) {
  const navigate = useNavigate()
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null)

  const workouts = (dayInfo?.workouts || []).filter((w: any) => w.workout_type !== 'rest')
  const isRest = workouts.length === 0

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">{displayDate}</h3>
        {isRest && dayInfo && (
          <span className="text-xs text-slate-600">Rest Day</span>
        )}
      </div>

      {workouts.length > 0 && (
        <div className="space-y-2">
          {workouts.map((w: any, idx: number) => {
            const Icon = SPORT_ICONS[w.sport] || SPORT_ICON_FALLBACK
            const isSource = swapSourceIndex === idx
            // `swapActive` is true whenever a swap is primed anywhere, even
            // on a different day than the one currently shown — that's
            // exactly the case (multi-workout target day) this panel exists
            // to handle, so target-eligibility can't be gated on
            // `swapSourceIndex` alone (that's only non-null when the source
            // happens to be on the day currently displayed).
            const isSwapTarget = swapActive && !isSource
            const isExpanded = expandedIdx === idx

            return (
              <div
                key={idx}
                className={`rounded-lg bg-bg-tertiary transition-colors ${
                  isSwapTarget ? 'ring-1 ring-accent/50 cursor-pointer' : ''
                }`}
                onClick={() => {
                  if (isSwapTarget) onSwapTargetClick(idx)
                }}
              >
                <div className="flex items-start gap-3 p-3">
                  <div className="p-1.5 rounded-lg bg-accent/10 mt-0.5">
                    <Icon className="w-4 h-4 text-accent" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 min-w-0">
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setExpandedIdx(isExpanded ? null : idx)
                        }}
                        className="min-w-0 text-sm font-medium text-left hover:text-accent transition-colors flex items-center gap-1"
                      >
                        <span className="truncate">{w.name}</span>
                        <ChevronDown className={`w-3 h-3 flex-shrink-0 text-slate-600 transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                      </button>
                      {(w.archetype || w.priority) && (
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 ${
                            ARCHETYPE_COLORS[w.archetype] ||
                            PRIORITY_COLORS[w.priority] ||
                            PRIORITY_COLORS.optional
                          }`}
                        >
                          {w.archetype || w.priority}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-1.5 text-xs text-slate-500">
                      {w.duration_minutes > 0 && <span className="tabular">{w.duration_minutes} min</span>}
                      {w.tss_estimate > 0 && <span className="tabular">{Math.round(w.tss_estimate)} TSS</span>}
                      {w.intensity_factor > 0 && <span className="tabular">IF {w.intensity_factor.toFixed(2)}</span>}
                      {w.target_zone && (
                        <span className="px-1.5 py-0.5 rounded bg-accent/10 text-accent">
                          {w.target_zone}
                        </span>
                      )}
                      <span className="px-1.5 py-0.5 rounded bg-white/5 capitalize">
                        {(w.workout_type || '').replace(/_/g, ' ')}
                      </span>
                    </div>
                  </div>
                  <div className="flex gap-1 flex-shrink-0">
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        onToggleSwapSource(idx)
                      }}
                      className={`p-1.5 rounded-lg transition-colors ${
                        isSource
                          ? 'bg-accent/20 text-accent'
                          : 'hover:bg-accent/10 text-slate-500 hover:text-accent'
                      }`}
                      title="Swap with another workout"
                    >
                      <ArrowLeftRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        if (!dayInfo) return
                        const details = `Skip week ${dayInfo.weekNumber} ${dayInfo.dayName} workout: ${w.name}`
                        adjust.mutate({ action: 'skip', details, week_number: dayInfo.weekNumber })
                      }}
                      className="p-1.5 rounded-lg hover:bg-danger/10 text-slate-500 hover:text-danger transition-colors"
                      title="Skip this workout"
                    >
                      <SkipForward className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        pushToWatch.mutate({ workout: w, date })
                      }}
                      disabled={pushToWatch.isPending}
                      className="p-1.5 rounded-lg hover:bg-success/10 text-slate-500 hover:text-success transition-colors disabled:opacity-50"
                      title="Push to watch via intervals.icu"
                    >
                      <Watch className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        api.downloadWorkoutFile(w, date)
                      }}
                      className="p-1.5 rounded-lg hover:bg-accent/10 text-slate-500 hover:text-accent transition-colors"
                      title="Download .fit — import into Garmin Connect or the COROS app"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                {isExpanded && (
                  <div className="px-3 pb-3 space-y-2 border-t border-white/5 pt-2 mx-3">
                    {w.description && (
                      <p className="text-xs text-slate-400 leading-relaxed">{w.description}</p>
                    )}
                    {w.coach_notes && (
                      <div className="text-xs text-slate-500 bg-bg-secondary rounded-lg p-2">
                        <span className="text-accent font-medium">Coach: </span>
                        {w.coach_notes}
                      </div>
                    )}
                    {w.steps && w.steps.length > 0 && (
                      <div className="space-y-1">
                        <span className="text-[10px] text-slate-600 uppercase tracking-wider">Workout Structure</span>
                        {w.steps.map((s: any, si: number) => (
                          <div key={si} className="flex items-start gap-2 text-xs text-slate-500">
                            <span className="w-16 text-right text-slate-600 flex-shrink-0 tabular">
                              {formatStep(s)}
                            </span>
                            <span className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${
                              s.type === 'warmup' ? 'bg-success' :
                              s.type === 'interval' ? 'bg-danger' :
                              s.type === 'rest' ? 'bg-info' :
                              s.type === 'cooldown' ? 'bg-sport-swimming' : 'bg-warning'
                            }`} />
                            <span className="min-w-0">
                              <span className="capitalize">{s.exercise || s.type}</span>
                              {s.power != null && <span className="text-slate-400"> {Math.round(s.power * 100)}% FTP</span>}
                              {s.pace != null && <span className="text-slate-400"> {formatPace(s.pace, w.sport)}</span>}
                              {(s.sets || s.repeat) > 1 && (
                                <span className="text-accent"> ×{s.sets || s.repeat}</span>
                              )}
                              {(s.cue || s.notes) && (
                                <span className="text-slate-600 italic"> — {s.cue || s.notes}</span>
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {!dayInfo && (
        <p className="text-xs text-slate-600">No planned workout for this day.</p>
      )}

      {/* Real activities logged this day */}
      {activities.length > 0 && (
        <div className="space-y-1.5 pt-1 border-t border-white/5">
          <span className="text-[10px] text-slate-600 uppercase tracking-wider">Logged</span>
          {activities.map((a: any) => {
            const badgeClass = SPORT_BADGE_CLASS[a.sport_type] || SPORT_BADGE_FALLBACK
            return (
              <button
                key={a.id}
                onClick={() => navigate(`/activities/${a.id}`)}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg bg-bg-tertiary hover:bg-bg-hover transition-colors text-left"
              >
                <span className={`text-[10px] px-1.5 py-0.5 rounded flex-shrink-0 capitalize ${badgeClass}`}>
                  {a.sport_type}
                </span>
                <span className="text-xs text-slate-300 truncate flex-1">{a.name || a.sport_type}</span>
                {a.tss > 0 && <span className="text-xs text-accent tabular flex-shrink-0">{Math.round(a.tss)} TSS</span>}
              </button>
            )
          })}
        </div>
      )}

      <div className="flex flex-col gap-1">
        {adjust.isPending && (
          <span className="flex items-center gap-1 text-xs text-accent">
            <Loader2 className="w-3 h-3 animate-spin" /> Adjusting...
          </span>
        )}
        {pushToWatch.isSuccess && (
          <p className="text-xs text-success">Workout pushed to intervals.icu for watch sync.</p>
        )}
        {pushToWatch.isError && (
          <p className="text-xs text-danger">{(pushToWatch.error as Error).message}</p>
        )}
      </div>
    </div>
  )
}
