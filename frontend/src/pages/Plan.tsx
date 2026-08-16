import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import {
  CalendarDays, Loader2, SkipForward, ArrowLeftRight,
  Watch, Dumbbell, Bike, Footprints,
  Waves, Zap, UserCog, ChevronDown, Trash2, AlertTriangle, TrendingUp, Download, Activity,
} from 'lucide-react'

const SPORT_ICONS: Record<string, typeof Bike> = {
  cycling: Bike,
  running: Footprints,
  swimming: Waves,
  strength: Dumbbell,
}

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

const WEEK_TYPE_COLORS: Record<string, string> = {
  build: 'bg-success/10 text-success',
  recovery: 'bg-info/10 text-info',
  taper: 'bg-sport-other/10 text-sport-other',
}

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const VOLUME_SOURCE_LABEL: Record<string, string> = {
  observed: 'Starting point taken from your synced training over the last few weeks.',
  stated: 'Starting point taken from the current volume you entered.',
  default: 'No training history yet — starting from a conservative default.',
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

type PlanNote = { id: string; text: string; hint?: string }

// Several independent bits of the generator (progression assessment, capacity
// mismatch, session-count shortfall, safety validation) can each produce a
// warning for the same plan. Shown as separate boxes that reads as alarming
// even when most of it is routine — fold them into one panel instead, and
// keep it collapsed past a couple of items so a plan with several minor notes
// doesn't read as more broken than it is.
function buildPlanNotes(planData: any): PlanNote[] {
  const notes: PlanNote[] = []
  if (planData?.progression_assessment?.note) {
    notes.push({ id: 'progression', text: planData.progression_assessment.note })
  }
  if (planData?.capacity_feedback) {
    notes.push({ id: 'capacity', text: planData.capacity_feedback })
  }
  const targets = planData?.session_targets
  // shortfall_expected === true means the gap is fully explained by
  // recovery/taper/ramp scaling — nothing for the athlete to act on, so it's
  // suppressed entirely rather than just downgraded.
  if (targets?.note && targets.shortfall_expected !== true) {
    notes.push({
      id: 'session-targets',
      text: `Could not fit every session you asked for — ${targets.note}.`,
      hint: 'Add hours, allow more sessions per day, or free up a rest day.',
    })
  }
  if (Array.isArray(planData?.safety_warnings)) {
    planData.safety_warnings.forEach((w: string, i: number) => {
      notes.push({ id: `safety-${i}`, text: w })
    })
  }
  return notes
}

function PlanNotes({ notes }: { notes: PlanNote[] }) {
  const [expanded, setExpanded] = useState(false)
  if (notes.length === 0) return null

  const VISIBLE = 2
  const shown = expanded ? notes : notes.slice(0, VISIBLE)
  const hiddenCount = notes.length - shown.length

  return (
    <div className="bg-warning/10 border border-warning/20 rounded-xl p-3 text-sm text-warning space-y-2">
      <div className="flex items-center gap-2">
        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
        <span className="font-medium">Plan notes</span>
        <span className="text-xs text-warning/70">({notes.length})</span>
      </div>
      <ul className="space-y-1.5 pl-6 list-disc marker:text-warning/50">
        {shown.map((n) => (
          <li key={n.id}>
            <span>{n.text}</span>
            {n.hint && <span className="block text-warning/70 text-xs mt-0.5">{n.hint}</span>}
          </li>
        ))}
      </ul>
      {!expanded && hiddenCount > 0 && (
        <button
          onClick={() => setExpanded(true)}
          className="text-xs text-warning/80 hover:text-warning underline underline-offset-2 ml-6"
        >
          Show {hiddenCount} more
        </button>
      )}
      {expanded && notes.length > VISIBLE && (
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-warning/80 hover:text-warning underline underline-offset-2 ml-6"
        >
          Show less
        </button>
      )}
    </div>
  )
}

function getWeeks(plan: any): any[] {
  if (plan?.weeks && Array.isArray(plan.weeks)) return plan.weeks
  if (plan?.days && Array.isArray(plan.days)) {
    return [{ week_number: 1, week_type: 'build', focus: '', target_hours: plan.total_hours, target_tss: plan.total_tss, days: plan.days }]
  }
  return []
}

// Locates the live `days` array inside a plan payload so an optimistic swap
// can mutate it directly, in whatever shape the plan actually uses
// (multi-week `weeks[]`, or a single flat `days[]`) — mirrors getWeeks above
// but returns a reference into the real object instead of a synthetic wrapper.
function findWeekDays(planData: any, weekNumber: number): any[] | null {
  if (planData?.weeks && Array.isArray(planData.weeks)) {
    return planData.weeks.find((w: any) => w.week_number === weekNumber)?.days ?? null
  }
  if (planData?.days && Array.isArray(planData.days)) {
    return planData.days
  }
  return null
}

export default function Plan() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [sports, setSports] = useState(['cycling', 'running'])
  const [hours, setHours] = useState(8)
  const [notes, setNotes] = useState('')
  const [swapSource, setSwapSource] = useState<{ weekIdx: number; day: string; idx: number } | null>(null)
  const [expandedWorkout, setExpandedWorkout] = useState<string | null>(null)
  const [activeWeek, setActiveWeek] = useState(0)

  const { data: plan, isLoading } = useQuery({
    queryKey: ['plan'],
    queryFn: () => api.currentPlan(),
  })

  const { data: profile } = useQuery({
    queryKey: ['profile'],
    queryFn: () => api.profile(),
  })

  const generate = useMutation({
    mutationFn: () => api.generatePlan({ sports, hours, notes: notes || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan'] })
      setActiveWeek(0)
    },
  })

  const adjust = useMutation({
    mutationFn: ({ action, details, week_number }: { action: string; details: string; week_number?: number }) =>
      api.adjustPlan(plan.id, action, details, week_number),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })

  // Swapping two workouts is a pure data move — no AI judgment call needed —
  // so it applies instantly against the local cache and persists deterministically
  // in the background, instead of paying for a slow full-week AI rewrite (the old
  // path, which also silently always targeted week 1 regardless of which week the
  // athlete was actually looking at).
  const swapWorkout = useMutation({
    mutationFn: (vars: { week_number: number; day_a: string; index_a: number; day_b: string; index_b: number }) =>
      api.swapWorkout({ plan_id: plan.id, ...vars }),
    onMutate: async (vars) => {
      await queryClient.cancelQueries({ queryKey: ['plan'] })
      const previous = queryClient.getQueryData(['plan'])
      queryClient.setQueryData(['plan'], (old: any) => {
        if (!old?.plan) return old
        const next = structuredClone(old)
        const days = findWeekDays(next.plan, vars.week_number)
        const dayA = days?.find((d: any) => d.day === vars.day_a)
        const dayB = days?.find((d: any) => d.day === vars.day_b)
        const wa = dayA?.workouts
        const wb = dayB?.workouts
        if (!wa || !wb || vars.index_a >= wa.length || vars.index_b >= wb.length) return old
        ;[wa[vars.index_a], wb[vars.index_b]] = [wb[vars.index_b], wa[vars.index_a]]
        return next
      })
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['plan'], context.previous)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })

  const pushToWatch = useMutation({
    mutationFn: ({ workout, date }: { workout: any; date: string }) =>
      api.pushToWatch(workout, date),
  })

  const pushWeek = useMutation({
    mutationFn: (weekNumber?: number) => api.pushPlan(plan.id, weekNumber),
  })

  const [copiedFeed, setCopiedFeed] = useState(false)

  const { data: compliance } = useQuery({
    queryKey: ['compliance', plan?.id],
    queryFn: () => api.planCompliance(plan.id),
    enabled: Boolean(plan?.id),
  })

  const adapt = useMutation({
    mutationFn: () => api.adaptPlan(plan.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan'] })
      queryClient.invalidateQueries({ queryKey: ['compliance'] })
      queryClient.invalidateQueries({ queryKey: ['calendar'] })
    },
  })

  const deletePlan = useMutation({
    mutationFn: (planId: number) => api.deletePlan(planId),
    onSuccess: () => {
      queryClient.setQueryData(['plan'], null)
      queryClient.invalidateQueries({ queryKey: ['plan'] })
      queryClient.invalidateQueries({ queryKey: ['calendar'] })
      setActiveWeek(0)
    },
  })

  const hasPlan = plan && plan.plan
  const weeks = hasPlan ? getWeeks(plan.plan) : []
  const currentWeek = weeks[activeWeek]

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <CalendarDays className="w-5 h-5 text-accent" /> Training Plan
        </h1>
        {hasPlan && (
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-xs text-slate-500 truncate">{plan.name}</span>
            {/* Without this the profile is unreachable once a plan exists — the
                onboarding entry point below only renders when there is none. */}
            <button
              onClick={() => navigate('/onboarding')}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 border border-white/10 hover:border-white/20 rounded-lg px-2.5 py-1.5 transition-colors shrink-0"
            >
              <UserCog className="w-3.5 h-3.5" />
              Edit setup
            </button>
          </div>
        )}
      </div>

      {!hasPlan && (
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
      )}

      {hasPlan && (
        <>
          {/* Plan description, volume ramp, capacity feedback */}
          <div className="space-y-2">
            {plan.plan.description && (
              <p className="text-sm text-slate-400 bg-bg-secondary rounded-xl border border-white/5 p-4">
                {plan.plan.description}
              </p>
            )}
            {plan.plan.progression_assessment?.peak_hours && (
              <div className="flex items-start gap-2 text-xs text-slate-500 bg-bg-secondary rounded-xl border border-white/5 px-4 py-2.5">
                <TrendingUp className="w-3.5 h-3.5 flex-shrink-0 text-accent mt-0.5" />
                <div>
                  <span>
                    Volume ramps{' '}
                    <span className="text-slate-300">
                      {plan.plan.progression_assessment.start_hours}h → {plan.plan.progression_assessment.peak_hours}h
                    </span>{' '}
                    per week over {plan.plan.progression_assessment.build_weeks} build weeks
                    {plan.plan.progression_assessment.weekly_increase_pct > 0 &&
                      ` (+${plan.plan.progression_assessment.weekly_increase_pct}% per build week)`}
                  </span>
                  <span className="block text-slate-600 mt-0.5">
                    {VOLUME_SOURCE_LABEL[plan.plan.progression_assessment.volume_source] ??
                      'Starting point from your profile.'}
                  </span>
                </div>
              </div>
            )}
            {plan.plan.progression_assessment?.readiness_note && (
              <div className="flex items-start gap-2 bg-info/10 border border-info/20 rounded-xl p-3 text-xs text-info">
                <Activity className="w-4 h-4 mt-0.5 flex-shrink-0" />
                <span>{plan.plan.progression_assessment.readiness_note}</span>
              </div>
            )}
            <PlanNotes notes={buildPlanNotes(plan.plan)} />
          </div>

          {/* Week tabs */}
          {weeks.length > 1 && (
            <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-hide">
              {weeks.map((w: any, i: number) => (
                <button
                  key={i}
                  onClick={() => setActiveWeek(i)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-colors flex items-center gap-1.5 ${
                    i === activeWeek
                      ? 'bg-accent/20 text-accent'
                      : 'bg-bg-secondary text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span>W{w.week_number}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                    WEEK_TYPE_COLORS[w.week_type] || 'bg-bg-tertiary text-slate-500'
                  }`}>
                    {w.week_type}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Current week header */}
          {currentWeek && (
            <div className="bg-bg-secondary rounded-xl border border-white/5 p-3 flex items-center justify-between">
              <div>
                <h2 className="text-sm font-medium">
                  Week {currentWeek.week_number}
                  <span className={`ml-2 px-1.5 py-0.5 rounded text-[10px] ${
                    WEEK_TYPE_COLORS[currentWeek.week_type] || ''
                  }`}>
                    {currentWeek.week_type}
                  </span>
                </h2>
                {currentWeek.focus && (
                  <p className="text-xs text-slate-500 mt-0.5">{currentWeek.focus}</p>
                )}
              </div>
              <div className="flex gap-3 text-xs text-slate-500">
                {currentWeek.target_hours && <span>{currentWeek.target_hours}h</span>}
                {currentWeek.target_tss && <span>{Math.round(currentWeek.target_tss)} TSS</span>}
                {currentWeek.distance_km && (
                  <span>
                    {Object.entries(currentWeek.distance_km as Record<string, number>)
                      .map(([s, km]) => `${km}km ${s}`)
                      .join(', ')}
                  </span>
                )}
              </div>
            </div>
          )}

          {/* How the finished weeks actually went */}
          {compliance?.weeks?.length > 0 && (
            <div className="bg-bg-secondary rounded-xl border border-white/5 p-4 space-y-3">
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-medium flex items-center gap-2">
                  <Activity className="w-4 h-4 text-accent" /> How it is going
                </h3>
                {compliance.typical_ratio != null && (
                  <span className="text-xs text-slate-500 tabular">
                    {Math.round(compliance.typical_ratio * 100)}% in a typical week
                  </span>
                )}
              </div>

              <div className="flex flex-wrap gap-1.5">
                {compliance.weeks.map((w: any) => {
                  const pct = w.ratio == null ? 0 : Math.round(w.ratio * 100)
                  const tone = pct >= 90 ? 'bg-success/20 text-success'
                    : pct >= 70 ? 'bg-warning/20 text-warning'
                    : 'bg-danger/20 text-danger'
                  return (
                    <span
                      key={w.week_number}
                      className={`text-[10px] px-2 py-1 rounded ${tone} tabular`}
                      title={`${w.completed_hours}h of ${w.planned_hours}h planned`}
                    >
                      W{w.week_number} {pct}%
                    </span>
                  )
                })}
              </div>

              <p className="text-xs text-slate-500">{compliance.recommendation?.reason}</p>

              {compliance.recommendation?.action !== 'none' && (
                <button
                  onClick={() => adapt.mutate()}
                  disabled={adapt.isPending}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-accent hover:bg-accent-hover text-bg-primary transition-colors disabled:opacity-50"
                >
                  {adapt.isPending
                    ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    : <TrendingUp className="w-3.5 h-3.5" />}
                  Adapt the weeks ahead
                </button>
              )}
              {adapt.isSuccess && (
                <p className="text-xs text-success">
                  {adapt.data?.adapted
                    ? `Updated ${adapt.data.weeks_changed} upcoming week(s).`
                    : adapt.data?.reason}
                </p>
              )}
              {adapt.isError && (
                <p className="text-xs text-danger">{(adapt.error as Error).message}</p>
              )}
            </div>
          )}

          {plan.plan.adaptation?.weeks_changed > 0 && (
            <div className="flex items-start gap-2 bg-info/10 border border-info/20 rounded-xl p-3 text-xs text-info">
              <Activity className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>
                Adapted {new Date(plan.plan.adaptation.applied_at).toLocaleDateString()} —
                {' '}{plan.plan.adaptation.weeks_changed} upcoming week(s) at{' '}
                {Math.round(plan.plan.adaptation.volume_factor * 100)}% volume
                {plan.plan.adaptation.dropped_sports?.length > 0 &&
                  `, one ${plan.plan.adaptation.dropped_sports.join(' and ')} session dropped`}.
              </span>
            </div>
          )}

          {/* Sync actions for the whole week / block */}
          {currentWeek && (
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => pushWeek.mutate(currentWeek.week_number)}
                disabled={pushWeek.isPending}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-bg-secondary border border-white/5 hover:bg-bg-hover transition-colors disabled:opacity-50"
              >
                {pushWeek.isPending
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Watch className="w-3.5 h-3.5" />}
                Send week {currentWeek.week_number} to watch
              </button>
              <button
                onClick={() => pushWeek.mutate(undefined)}
                disabled={pushWeek.isPending}
                className="px-3 py-1.5 text-xs rounded-lg bg-bg-secondary border border-white/5 hover:bg-bg-hover transition-colors disabled:opacity-50"
              >
                Send whole plan
              </button>
              <button
                onClick={() => {
                  // The URL now comes from the server, so it is not known at
                  // click time. Hand the promise to the clipboard rather than
                  // awaiting first — Safari rejects a write that resumes after
                  // an await, and Chrome accepts either form.
                  const url = api.planCalendarUrl(plan.id)
                  navigator.clipboard
                    .write([new ClipboardItem({ 'text/plain': url.then((u) => new Blob([u], { type: 'text/plain' })) })])
                    .catch(async () => navigator.clipboard.writeText(await url))
                    .then(() => {
                      setCopiedFeed(true)
                      setTimeout(() => setCopiedFeed(false), 3000)
                    })
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-bg-secondary border border-white/5 hover:bg-bg-hover transition-colors"
                title="Subscribe to this plan from any calendar app"
              >
                <CalendarDays className="w-3.5 h-3.5" />
                {copiedFeed ? 'Feed URL copied' : 'Copy calendar feed'}
              </button>
              {pushWeek.isSuccess && (
                <span className="text-xs text-success">
                  Sent {pushWeek.data?.count} session(s) to intervals.icu
                </span>
              )}
              {pushWeek.isError && (
                <span className="text-xs text-danger">{(pushWeek.error as Error).message}</span>
              )}
            </div>
          )}

          {currentWeek?.volume_note && (
            <div className="flex items-start gap-2 bg-warning/10 border border-warning/20 rounded-xl p-3 text-xs text-warning">
              <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span>{currentWeek.volume_note}</span>
            </div>
          )}

          {/* Day cards */}
          {currentWeek && (
            <div className="grid gap-3">
              {DAYS.map((day) => {
                const dayData = currentWeek.days?.find(
                  (d: any) => d.day?.toLowerCase() === day
                )
                const workouts = (dayData?.workouts || []).filter(
                  (w: any) => w.workout_type !== 'rest'
                )
                const isRest = workouts.length === 0

                return (
                  <div
                    key={day}
                    className={`min-w-0 bg-bg-secondary rounded-xl border border-white/5 ${
                      isRest ? 'p-3' : 'p-4'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium capitalize flex items-center gap-2">
                        {day}
                        {dayData?.date && (
                          <span className="text-xs text-slate-500">{dayData.date}</span>
                        )}
                      </h3>
                      {isRest && (
                        <span className="text-xs text-slate-600">Rest Day</span>
                      )}
                    </div>

                    {workouts.length > 0 && (
                      <div className="space-y-2 mt-2">
                        {workouts.map((w: any, idx: number) => {
                          const Icon = SPORT_ICONS[w.sport] || Zap
                          const isSwapTarget =
                            swapSource && (swapSource.weekIdx !== activeWeek || swapSource.day !== day || swapSource.idx !== idx)
                          const workoutKey = `${activeWeek}-${day}-${idx}`
                          const isExpanded = expandedWorkout === workoutKey

                          return (
                            <div
                              key={idx}
                              className={`rounded-lg bg-bg-tertiary transition-colors ${
                                isSwapTarget ? 'ring-1 ring-accent/50 cursor-pointer' : ''
                              }`}
                              onClick={() => {
                                if (isSwapTarget && swapSource && currentWeek?.week_number != null) {
                                  swapWorkout.mutate({
                                    week_number: currentWeek.week_number,
                                    day_a: swapSource.day,
                                    index_a: swapSource.idx,
                                    day_b: day,
                                    index_b: idx,
                                  })
                                  setSwapSource(null)
                                }
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
                                        setExpandedWorkout(isExpanded ? null : workoutKey)
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
                                      if (swapSource?.weekIdx === activeWeek && swapSource?.day === day && swapSource?.idx === idx) {
                                        setSwapSource(null)
                                      } else {
                                        setSwapSource({ weekIdx: activeWeek, day, idx })
                                      }
                                    }}
                                    className={`p-1.5 rounded-lg transition-colors ${
                                      swapSource?.weekIdx === activeWeek && swapSource?.day === day && swapSource?.idx === idx
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
                                      const details = `Skip week ${currentWeek.week_number} ${day} workout: ${w.name}`
                                      adjust.mutate({ action: 'skip', details, week_number: currentWeek.week_number })
                                    }}
                                    className="p-1.5 rounded-lg hover:bg-danger/10 text-slate-500 hover:text-danger transition-colors"
                                    title="Skip this workout"
                                  >
                                    <SkipForward className="w-3.5 h-3.5" />
                                  </button>
                                  {dayData?.date && (
                                    <>
                                      <button
                                        onClick={(e) => {
                                          e.stopPropagation()
                                          pushToWatch.mutate({ workout: w, date: dayData.date })
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
                                          api.downloadWorkoutFile(w, dayData.date)
                                        }}
                                        className="p-1.5 rounded-lg hover:bg-accent/10 text-slate-500 hover:text-accent transition-colors"
                                        title="Download .fit — import into Garmin Connect or the COROS app"
                                      >
                                        <Download className="w-3.5 h-3.5" />
                                      </button>
                                    </>
                                  )}
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
                  </div>
                )
              })}
            </div>
          )}

          {/* Plan-level info and actions */}
          {plan.plan.progression_notes && (
            <p className="text-xs text-slate-500 bg-bg-secondary rounded-xl border border-white/5 p-3 italic">
              {plan.plan.progression_notes}
            </p>
          )}

          <div className="flex items-center justify-between text-xs text-slate-500 bg-bg-secondary rounded-xl border border-white/5 p-4">
            <div className="flex gap-4">
              {plan.plan.total_weeks && <span>{plan.plan.total_weeks} weeks</span>}
              {plan.plan.total_distance_km && (
                <span>
                  {Object.entries(plan.plan.total_distance_km as Record<string, number>)
                    .map(([s, km]) => `${km}km ${s}`)
                    .join(', ')}
                </span>
              )}
            </div>
            <div className="flex gap-2">
              {adjust.isPending && (
                <span className="flex items-center gap-1 text-accent">
                  <Loader2 className="w-3 h-3 animate-spin" /> Adjusting...
                </span>
              )}
              <button
                onClick={() => {
                  if (confirm('Delete this training plan? This cannot be undone.')) {
                    deletePlan.mutate(plan.id)
                  }
                }}
                disabled={deletePlan.isPending}
                className="px-3 py-1.5 rounded-lg bg-danger/10 hover:bg-danger/20 text-danger transition-colors disabled:opacity-50 flex items-center gap-1.5"
              >
                <Trash2 className="w-3 h-3" />
                {deletePlan.isPending ? 'Deleting...' : 'Delete Plan'}
              </button>
              <button
                onClick={() => {
                  queryClient.setQueryData(['plan'], null)
                }}
                className="px-3 py-1.5 rounded-lg bg-bg-tertiary hover:bg-bg-hover transition-colors"
              >
                New Plan
              </button>
            </div>
          </div>

          {pushToWatch.isSuccess && (
            <p className="text-xs text-success">Workout pushed to intervals.icu for watch sync.</p>
          )}
          {pushToWatch.isError && (
            <p className="text-xs text-danger">{(pushToWatch.error as Error).message}</p>
          )}
        </>
      )}
    </div>
  )
}
