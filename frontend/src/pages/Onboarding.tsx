import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import {
  Zap, ChevronRight, ChevronLeft, Loader2,
  Bike, Footprints, Waves, Dumbbell, Target,
  Calendar, Clock, Wrench, Check, Info,
} from 'lucide-react'

const STEPS = ['About You', 'Goals', 'Weaknesses', 'Schedule', 'Equipment', 'Review']

const EXPERIENCE_LEVELS = [
  { value: 'beginner', label: 'Beginner', desc: 'Training < 1 year, building base fitness' },
  { value: 'intermediate', label: 'Intermediate', desc: '1-3 years, consistent training' },
  { value: 'advanced', label: 'Advanced', desc: '3+ years, structured training experience' },
]

const GOALS = [
  { value: 'general_fitness', label: 'General Fitness', desc: 'Stay fit, enjoy training' },
  { value: 'event', label: 'Event / Race', desc: 'Prepare for a specific event' },
  { value: 'performance', label: 'Performance', desc: 'Maximize FTP / speed / power' },
  { value: 'weight_loss', label: 'Health & Weight', desc: 'Body composition focus' },
]

const SPORTS = [
  { value: 'cycling', label: 'Cycling', icon: Bike },
  { value: 'running', label: 'Running', icon: Footprints },
  { value: 'swimming', label: 'Swimming', icon: Waves },
  { value: 'strength', label: 'Strength', icon: Dumbbell },
]

const ABILITIES = [
  { value: 'endurance', label: 'Endurance', desc: 'Long sustained efforts' },
  { value: 'threshold', label: 'Threshold', desc: 'FTP / lactate threshold' },
  { value: 'vo2max', label: 'VO2max', desc: 'High-intensity capacity' },
  { value: 'sprint', label: 'Sprint', desc: 'Short explosive power' },
  { value: 'climbing', label: 'Climbing', desc: 'W/kg, sustained climbing' },
  { value: 'tempo', label: 'Tempo', desc: 'Sub-threshold endurance' },
]

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

const PLAN_DURATIONS = [
  { value: 4, label: '4 weeks' },
  { value: 8, label: '8 weeks' },
  { value: 12, label: '12 weeks' },
  { value: 16, label: '16 weeks' },
]

export default function Onboarding() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [step, setStep] = useState(0)

  const [profile, setProfile] = useState({
    experience_level: '',
    primary_sport: 'cycling',
    goal: '',
    goal_event: '',
    goal_date: '',
    weaknesses: [] as string[],
    strengths: [] as string[],
    sports: ['cycling'] as string[],
    weekly_hours: 8,
    current_weekly_hours: null as number | null,
    max_sessions_per_day: 1,
    sport_limits: {} as Record<string, any>,
    preferred_hard_days: ['tuesday', 'thursday', 'saturday'] as string[],
    preferred_rest_days: ['monday'] as string[],
    plan_duration_weeks: 8,
    has_trainer: false,
    has_power_meter: false,
    has_hr_monitor: true,
    auto_push: false,
    recovery_mode: 'auto' as 'auto' | 'extended' | 'off',
    recovery_cycle_weeks: null as number | null,
    volume_progression_mode: 'ramp' as 'ramp' | 'steady',
    training_style: 'standard' as 'standard' | 'norwegian',
    notes: '',
  })

  // Editing an existing profile should start from what is already saved —
  // otherwise "Update Profile" quietly discards it and asks for all six steps
  // again.
  const { data: saved } = useQuery({ queryKey: ['profile'], queryFn: () => api.profile() })
  const seeded = useRef(false)

  useEffect(() => {
    if (!saved || seeded.current) return
    seeded.current = true
    setProfile((current) => {
      const merged: any = { ...current }
      for (const [key, value] of Object.entries(saved)) {
        if (key in merged && value !== null && value !== undefined && value !== '') {
          merged[key] = value
        }
      }
      return merged
    })
  }, [saved])

  const saveProfile = useMutation({
    mutationFn: () => api.updateProfile({ ...profile, onboarding_complete: true }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profile'] })
    },
  })

  const [elapsed, setElapsed] = useState(0)
  const [planStart, setPlanStart] = useState<'this_week' | 'next_week'>('next_week')

  const generatePlan = useMutation({
    mutationFn: () => api.generateFullPlanAndWait(setElapsed, planStart),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['plan'] })
      navigate('/plan')
    },
  })

  const update = (field: string, value: any) => {
    setProfile((p) => ({ ...p, [field]: value }))
  }

  const toggleList = (field: string, value: string) => {
    setProfile((p) => {
      const list = (p as any)[field] as string[]
      return {
        ...p,
        [field]: list.includes(value) ? list.filter((v) => v !== value) : [...list, value],
      }
    })
  }

  const canProceed = () => {
    switch (step) {
      case 0: return profile.experience_level && profile.sports.length > 0
      case 1: return profile.goal
      case 2: return true
      case 3: return profile.weekly_hours > 0
      case 4: return true
      case 5: return true
      default: return true
    }
  }

  const handleFinish = async () => {
    await saveProfile.mutateAsync()
    generatePlan.mutate()
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-xl">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Zap className="w-7 h-7 text-accent" />
            <span className="text-2xl font-bold">Pulse</span>
          </div>
          <p className="text-sm text-slate-400">Set up your training profile</p>
        </div>

        {/* Progress */}
        <div className="flex gap-1 mb-8">
          {STEPS.map((s, i) => (
            <div key={s} className="flex-1 flex flex-col items-center gap-1">
              <div
                className={`h-1 w-full rounded-full transition-colors ${
                  i <= step ? 'bg-accent' : 'bg-bg-tertiary'
                }`}
              />
              <span className={`text-[10px] ${i === step ? 'text-accent' : 'text-slate-600'}`}>
                {s}
              </span>
            </div>
          ))}
        </div>

        <div className="bg-bg-secondary rounded-2xl border border-white/5 p-6 min-h-[360px] flex flex-col">
          <div className="flex-1">
            {step === 0 && (
              <StepAbout
                profile={profile}
                update={update}
                toggleList={toggleList}
              />
            )}
            {step === 1 && (
              <StepGoals profile={profile} update={update} />
            )}
            {step === 2 && (
              <StepWeaknesses profile={profile} toggleList={toggleList} />
            )}
            {step === 3 && (
              <StepSchedule profile={profile} update={update} toggleList={toggleList} />
            )}
            {step === 4 && (
              <StepEquipment profile={profile} update={update} />
            )}
            {step === 5 && (
              <StepReview
                profile={profile}
                update={update}
                planStart={planStart}
                setPlanStart={setPlanStart}
                isGenerating={generatePlan.isPending || saveProfile.isPending}
              />
            )}
          </div>

          {/* Navigation */}
          <div className="flex items-center justify-between mt-6 pt-4 border-t border-white/5">
            <button
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              className="flex items-center gap-1 px-3 py-2 text-sm text-slate-400 hover:text-slate-200 disabled:opacity-30 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" /> Back
            </button>

            {step < STEPS.length - 1 ? (
              <button
                onClick={() => setStep((s) => s + 1)}
                disabled={!canProceed()}
                className="flex items-center gap-1 px-5 py-2 text-sm bg-accent hover:bg-accent-hover text-bg-primary rounded-lg disabled:opacity-30 transition-colors"
              >
                Next <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleFinish}
                disabled={generatePlan.isPending || saveProfile.isPending}
                className="flex items-center gap-2 px-5 py-2 text-sm bg-accent hover:bg-accent-hover text-bg-primary rounded-lg disabled:opacity-50 transition-colors"
              >
                {generatePlan.isPending || saveProfile.isPending ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Generating Plan{elapsed ? ` — ${elapsed}s` : '...'}
                  </>
                ) : (
                  <><Zap className="w-4 h-4" /> Generate Plan</>
                )}
              </button>
            )}
          </div>

          {generatePlan.isPending && (
            <p className="text-xs text-slate-500 mt-2 text-center">
              Writing every session of your block — this takes a few minutes.
              You can leave this page; the plan keeps building on the server.
            </p>
          )}

          {generatePlan.isError && (
            <p className="text-xs text-danger mt-2 text-center">
              {(generatePlan.error as Error).message}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}

function StepAbout({ profile, update, toggleList }: any) {
  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <h2 className="text-lg font-semibold">Experience Level</h2>
          <div className="group relative">
            <Info className="w-4 h-4 text-slate-500 cursor-help" />
            <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-64 p-2.5 rounded-xl bg-bg-tertiary border border-white/10 text-xs text-slate-300 leading-relaxed opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-10">
              This refers to structured endurance training (cycling, running, swimming). Years of lifting or team sports don't count — if you're new to endurance, start with Beginner.
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-500 mb-3">How long have you been doing structured endurance training?</p>
        <div className="space-y-2">
          {EXPERIENCE_LEVELS.map((lvl) => (
            <button
              key={lvl.value}
              onClick={() => update('experience_level', lvl.value)}
              className={`w-full text-left p-3 rounded-xl transition-colors ${
                profile.experience_level === lvl.value
                  ? 'bg-accent/15 border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{lvl.label}</div>
              <div className="text-xs text-slate-500">{lvl.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-1">Sports</h2>
        <p className="text-xs text-slate-500 mb-3">Which sports do you train?</p>
        <div className="grid grid-cols-2 gap-2">
          {SPORTS.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.value}
                onClick={() => toggleList('sports', s.value)}
                className={`flex items-center gap-2 p-3 rounded-xl transition-colors ${
                  profile.sports.includes(s.value)
                    ? 'bg-accent/15 border border-accent/30'
                    : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
                }`}
              >
                <Icon className="w-5 h-5" />
                <span className="text-sm">{s.label}</span>
              </button>
            )
          })}
        </div>
      </div>
    </div>
  )
}

function StepGoals({ profile, update }: any) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
          <Target className="w-5 h-5 text-accent" /> Training Goal
        </h2>
        <p className="text-xs text-slate-500 mb-3">What are you training for?</p>
        <div className="space-y-2">
          {GOALS.map((g) => (
            <button
              key={g.value}
              onClick={() => update('goal', g.value)}
              className={`w-full text-left p-3 rounded-xl transition-colors ${
                profile.goal === g.value
                  ? 'bg-accent/15 border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{g.label}</div>
              <div className="text-xs text-slate-500">{g.desc}</div>
            </button>
          ))}
        </div>
      </div>

      {profile.goal === 'event' && (
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Event Name</label>
            <input
              type="text"
              value={profile.goal_event}
              onChange={(e) => update('goal_event', e.target.value)}
              placeholder="e.g. Gran Fondo, Marathon, Sprint Triathlon"
              className="w-full bg-bg-tertiary text-sm rounded-xl px-3 py-2.5 border border-white/5 placeholder:text-slate-600"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1 flex items-center gap-1">
              <Calendar className="w-3 h-3" /> Event Date
            </label>
            <input
              type="date"
              value={profile.goal_date}
              onChange={(e) => update('goal_date', e.target.value)}
              className="w-full bg-bg-tertiary text-sm rounded-xl px-3 py-2.5 border border-white/5"
            />
          </div>
        </div>
      )}
    </div>
  )
}

function StepWeaknesses({ profile, toggleList }: any) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold mb-1">Weaknesses</h2>
        <p className="text-xs text-slate-500 mb-3">What areas need the most work? The plan will prioritize these.</p>
        <div className="grid grid-cols-2 gap-2">
          {ABILITIES.map((a) => (
            <button
              key={a.value}
              onClick={() => toggleList('weaknesses', a.value)}
              className={`text-left p-3 rounded-xl transition-colors ${
                profile.weaknesses.includes(a.value)
                  ? 'bg-danger/10 border border-danger/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{a.label}</div>
              <div className="text-[11px] text-slate-500">{a.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-1">Strengths</h2>
        <p className="text-xs text-slate-500 mb-3">What are you already good at? The plan will maintain these.</p>
        <div className="grid grid-cols-2 gap-2">
          {ABILITIES.map((a) => (
            <button
              key={a.value}
              onClick={() => toggleList('strengths', a.value)}
              className={`text-left p-3 rounded-xl transition-colors ${
                profile.strengths.includes(a.value)
                  ? 'bg-success/10 border border-success/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{a.label}</div>
              <div className="text-[11px] text-slate-500">{a.desc}</div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

const MAX_SESSIONS_PER_SPORT = 8

/** Per-discipline weekly frequency. Left on Auto, the planner derives it from
 *  volume; set, it becomes the number the plan is built around. */
function SessionsPerSport({ profile, update }: any) {
  const sports = SPORTS.filter(
    (s) => s.value !== 'strength' && profile.sports.includes(s.value),
  )
  if (sports.length === 0) return null

  const limits: Record<string, any> = profile.sport_limits || {}
  const sessionsFor = (sport: string): number | null => limits[sport]?.sessions ?? null
  const longDayFor = (sport: string): string | null => limits[sport]?.long_day ?? null
  const lockFor = (sport: string): boolean => Boolean(limits[sport]?.lock_sessions)

  const setLimit = (sport: string, key: string, value: any) => {
    const entry = { ...(limits[sport] || {}) }
    if (value === null || value === false) delete entry[key]
    else entry[key] = value
    const next = { ...limits, [sport]: entry }
    // Drop the key entirely once nothing is set, so an untouched profile keeps
    // sending {} and the planner stays on its own frequency model.
    if (Object.keys(entry).length === 0) delete next[sport]
    update('sport_limits', next)
  }

  const setSessions = (sport: string, value: number | null) => setLimit(sport, 'sessions', value)
  const setLongDay = (sport: string, value: string | null) => setLimit(sport, 'long_day', value)
  const setLock = (sport: string, value: boolean) => setLimit(sport, 'lock_sessions', value)

  const chosen = sports.filter((s) => sessionsFor(s.value) !== null)
  const total = chosen.reduce((sum, s) => sum + (sessionsFor(s.value) || 0), 0)
  const restDays = profile.preferred_rest_days?.length || 0
  const capacity = (7 - restDays) * (profile.max_sessions_per_day || 1)
  const overCapacity = chosen.length === sports.length && total > capacity

  return (
    <div>
      <h2 className="text-sm font-medium mb-1 flex items-center gap-2">
        Sessions Per Sport
        <div className="group relative">
          <Info className="w-3.5 h-3.5 text-slate-500 cursor-help" />
          <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-64 p-2.5 rounded-xl bg-bg-tertiary border border-white/10 text-xs text-slate-300 leading-relaxed opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-10">
            Leave on Auto and frequency follows your volume. Set a number and the plan is built around it — extra hours make those sessions longer rather than adding more.
          </div>
        </div>
      </h2>
      <p className="text-xs text-slate-500 mb-3">
        Know you want 6 rides and 3 runs? Set them here.
      </p>

      <div className="space-y-2">
        {sports.map((sport) => {
          const Icon = sport.icon
          const value = sessionsFor(sport.value)
          const longDay = longDayFor(sport.value)
          const locked = lockFor(sport.value)
          return (
            <div
              key={sport.value}
              className="p-2.5 rounded-xl bg-bg-tertiary border border-white/5 space-y-2"
            >
              <div className="flex items-center gap-3">
                <Icon className="w-4 h-4 text-slate-400 shrink-0" />
                <span className="text-sm flex-1 min-w-0 truncate">{sport.label}</span>
                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setSessions(sport.value, null)}
                    className={`px-2.5 py-1 text-[11px] rounded-lg transition-colors ${
                      value === null
                        ? 'bg-accent/20 text-accent border border-accent/30'
                        : 'text-slate-500 border border-transparent hover:text-slate-300'
                    }`}
                  >
                    Auto
                  </button>
                  <button
                    onClick={() => setSessions(sport.value, Math.max(1, (value ?? 1) - 1))}
                    disabled={value !== null && value <= 1}
                    className="w-7 h-7 rounded-lg bg-bg-hover text-slate-300 disabled:opacity-30 hover:text-white transition-colors"
                    aria-label={`Fewer ${sport.label} sessions`}
                  >
                    −
                  </button>
                  <span
                    className={`w-6 text-center text-sm tabular-nums ${
                      value === null ? 'text-slate-600' : 'font-medium'
                    }`}
                  >
                    {value ?? '–'}
                  </span>
                  <button
                    onClick={() =>
                      setSessions(sport.value, Math.min(MAX_SESSIONS_PER_SPORT, (value ?? 0) + 1))
                    }
                    disabled={value !== null && value >= MAX_SESSIONS_PER_SPORT}
                    className="w-7 h-7 rounded-lg bg-bg-hover text-slate-300 disabled:opacity-30 hover:text-white transition-colors"
                    aria-label={`More ${sport.label} sessions`}
                  >
                    +
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 pl-7 flex-wrap">
                <label className="text-[11px] text-slate-500 shrink-0">Long day</label>
                <select
                  value={longDay ?? ''}
                  onChange={(e) => setLongDay(sport.value, e.target.value || null)}
                  className="bg-bg-hover text-[11px] rounded-lg px-2 py-1 border border-white/5 text-slate-300 capitalize"
                >
                  <option value="">Auto</option>
                  {DAYS.map((d) => (
                    <option key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</option>
                  ))}
                </select>

                <button
                  onClick={() => setLock(sport.value, !locked)}
                  disabled={value === null}
                  title={value === null ? 'Set a session count first' : undefined}
                  className={`flex items-center gap-1.5 px-2 py-1 text-[11px] rounded-lg border transition-colors disabled:opacity-30 ${
                    locked
                      ? 'bg-accent/15 border-accent/30 text-accent'
                      : 'bg-transparent border-white/10 text-slate-500 hover:text-slate-300'
                  }`}
                >
                  <span className={`w-3 h-3 rounded-sm border flex items-center justify-center ${
                    locked ? 'bg-accent border-accent' : 'border-slate-500'
                  }`}>
                    {locked && <Check className="w-2.5 h-2.5 text-bg-primary" />}
                  </span>
                  Keep this count every week
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {chosen.length > 0 && (
        <p className={`text-[11px] mt-2 ${overCapacity ? 'text-warning' : 'text-slate-500'}`}>
          {overCapacity
            ? `${total} sessions needs more room than ${7 - restDays} days at ${
                profile.max_sessions_per_day
              }/day (${capacity}). Raise sessions per day, or train on a rest day.`
            : `${total} session${total === 1 ? '' : 's'} a week set${
                chosen.length < sports.length ? `, ${sports.length - chosen.length} on Auto` : ''
              }.`}
        </p>
      )}
    </div>
  )
}

function StepSchedule({ profile, update, toggleList }: any) {
  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
          <Clock className="w-5 h-5 text-accent" /> Weekly Hours
        </h2>
        <p className="text-xs text-slate-500 mb-3">How many hours per week can you train?</p>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={3}
            max={20}
            step={0.5}
            value={profile.weekly_hours}
            onChange={(e) => update('weekly_hours', Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-xl font-bold min-w-[50px] text-right">{profile.weekly_hours}h</span>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-1 flex items-center gap-2">
          Training Now
          <div className="group relative">
            <Info className="w-3.5 h-3.5 text-slate-500 cursor-help" />
            <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-60 p-2.5 rounded-xl bg-bg-tertiary border border-white/10 text-xs text-slate-300 leading-relaxed opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-10">
              Your plan starts here and builds toward your available hours. Jumping straight to full volume is how people get hurt.
            </div>
          </div>
        </h2>
        <p className="text-xs text-slate-500 mb-3">
          How many hours per week are you training at the moment?
        </p>
        <div className="flex items-center gap-3">
          <input
            type="range"
            min={0}
            max={profile.weekly_hours}
            step={0.5}
            value={profile.current_weekly_hours ?? profile.weekly_hours}
            onChange={(e) => update('current_weekly_hours', Number(e.target.value))}
            className="flex-1 accent-accent"
          />
          <span className="text-xl font-bold min-w-[50px] text-right">
            {profile.current_weekly_hours ?? profile.weekly_hours}h
          </span>
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2">Volume Progression</h2>
        <p className="text-xs text-slate-500 mb-2">How should weekly volume build toward your target?</p>
        <div className="flex gap-2">
          {[
            { value: 'ramp', label: 'Ramp', desc: 'Steadily climbs to your target' },
            { value: 'steady', label: 'Steady', desc: 'Ramps in briefly, then holds flat' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => update('volume_progression_mode', opt.value)}
              className={`flex-1 min-w-0 text-left p-3 rounded-xl transition-colors ${
                profile.volume_progression_mode === opt.value
                  ? 'bg-accent/15 border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{opt.label}</div>
              <div className="text-[11px] text-slate-500">{opt.desc}</div>
            </button>
          ))}
        </div>
        {profile.volume_progression_mode === 'steady' && (
          <p className="text-[11px] text-slate-500 mt-2">
            Steady still ramps in for the first few weeks and won't jump more than ~15% above
            your recent training — it's not a way to start at full volume cold.
          </p>
        )}
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2 flex items-center gap-2">
          Sessions Per Day
          <div className="group relative">
            <Info className="w-3.5 h-3.5 text-slate-500 cursor-help" />
            <div className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 w-60 p-2.5 rounded-xl bg-bg-tertiary border border-white/10 text-xs text-slate-300 leading-relaxed opacity-0 pointer-events-none group-hover:opacity-100 group-hover:pointer-events-auto transition-opacity z-10">
              With 2 sessions, hard days get an easy AM ride + PM intensity session. Adds volume without extra fatigue.
            </div>
          </div>
        </h2>
        <p className="text-xs text-slate-500 mb-2">How often can you train in one day?</p>
        <div className="flex gap-2">
          {[
            { value: 1, label: '1', desc: 'Standard' },
            { value: 2, label: '2', desc: 'AM + PM' },
            { value: 3, label: '3', desc: 'High frequency' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => update('max_sessions_per_day', opt.value)}
              className={`flex-1 min-w-0 text-left p-3 rounded-xl transition-colors ${
                profile.max_sessions_per_day === opt.value
                  ? 'bg-accent/15 border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{opt.label}/day</div>
              <div className="text-[11px] text-slate-500 truncate">{opt.desc}</div>
            </button>
          ))}
        </div>
      </div>

      <SessionsPerSport profile={profile} update={update} />

      <div>
        <h2 className="text-sm font-medium mb-2">Hard Days</h2>
        <p className="text-xs text-slate-500 mb-2">When can you do quality / high-intensity sessions?</p>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((d) => (
            <button
              key={d}
              onClick={() => toggleList('preferred_hard_days', d)}
              className={`px-3 py-1.5 text-xs rounded-lg capitalize transition-colors ${
                profile.preferred_hard_days.includes(d)
                  ? 'bg-accent/20 text-accent border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 text-slate-500 hover:text-slate-300'
              }`}
            >
              {d.slice(0, 3)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2">Rest Days</h2>
        <p className="text-xs text-slate-500 mb-2">Which days do you prefer off?</p>
        <div className="flex flex-wrap gap-1.5">
          {DAYS.map((d) => (
            <button
              key={d}
              onClick={() => toggleList('preferred_rest_days', d)}
              className={`px-3 py-1.5 text-xs rounded-lg capitalize transition-colors ${
                profile.preferred_rest_days.includes(d)
                  ? 'bg-success/15 text-success border border-success/30'
                  : 'bg-bg-tertiary border border-white/5 text-slate-500 hover:text-slate-300'
              }`}
            >
              {d.slice(0, 3)}
            </button>
          ))}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2">Recovery Weeks</h2>
        <p className="text-xs text-slate-500 mb-2">How often should the plan back off for a recovery week?</p>
        <div className="flex gap-2">
          {[
            { value: 'auto', label: 'Auto', desc: 'Derived from experience' },
            { value: 'extended', label: 'Extended', desc: 'Longer build cycles' },
            { value: 'off', label: 'Off', desc: 'Only when forced' },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => update('recovery_mode', opt.value)}
              className={`flex-1 min-w-0 text-left p-3 rounded-xl transition-colors ${
                profile.recovery_mode === opt.value
                  ? 'bg-accent/15 border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
              }`}
            >
              <div className="text-sm font-medium">{opt.label}</div>
              <div className="text-[11px] text-slate-500 truncate">{opt.desc}</div>
            </button>
          ))}
        </div>
        {profile.recovery_mode === 'extended' && (
          <div className="flex items-center gap-3 mt-2">
            <label className="text-xs text-slate-400">Build cycle length</label>
            <input
              type="number"
              min={1}
              max={8}
              value={profile.recovery_cycle_weeks ?? ''}
              placeholder="weeks"
              onChange={(e) => {
                const raw = e.target.value
                if (raw === '') { update('recovery_cycle_weeks', null); return }
                const clamped = Math.min(8, Math.max(1, Number(raw)))
                update('recovery_cycle_weeks', clamped)
              }}
              className="w-20 bg-bg-tertiary text-sm rounded-lg px-2 py-1.5 border border-white/5"
            />
            <span className="text-xs text-slate-500">weeks between recovery weeks</span>
          </div>
        )}
        <p className="text-[11px] text-slate-500 mt-2">
          Off still forces a recovery week after a stretch of hard weeks — it's not a true disable.
        </p>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2">Plan Duration</h2>
        <div className="flex gap-2">
          {PLAN_DURATIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => update('plan_duration_weeks', d.value)}
              className={`px-3 py-2 text-xs rounded-lg transition-colors ${
                profile.plan_duration_weeks === d.value
                  ? 'bg-accent/20 text-accent border border-accent/30'
                  : 'bg-bg-tertiary border border-white/5 text-slate-400'
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}

function StepEquipment({ profile, update }: any) {
  const items = [
    { field: 'has_trainer', label: 'Smart Trainer', desc: 'Indoor trainer with ERG mode (FTMS)', icon: Bike },
    { field: 'has_power_meter', label: 'Power Meter', desc: 'Outdoor power measurement', icon: Zap },
    { field: 'has_hr_monitor', label: 'HR Monitor', desc: 'Chest strap or optical HR', icon: Target },
  ]

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-lg font-semibold mb-1 flex items-center gap-2">
          <Wrench className="w-5 h-5 text-accent" /> Equipment
        </h2>
        <p className="text-xs text-slate-500 mb-3">What training equipment do you have?</p>
        <div className="space-y-2">
          {items.map((item) => {
            const Icon = item.icon
            return (
              <button
                key={item.field}
                onClick={() => update(item.field, !(profile as any)[item.field])}
                className={`w-full flex items-center gap-3 p-3 rounded-xl transition-colors ${
                  (profile as any)[item.field]
                    ? 'bg-accent/15 border border-accent/30'
                    : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
                }`}
              >
                <div className={`p-2 rounded-lg ${(profile as any)[item.field] ? 'bg-accent/20' : 'bg-bg-hover'}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="text-left flex-1">
                  <div className="text-sm font-medium">{item.label}</div>
                  <div className="text-xs text-slate-500">{item.desc}</div>
                </div>
                {(profile as any)[item.field] && <Check className="w-4 h-4 text-accent" />}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <h2 className="text-sm font-medium mb-2">Auto-Push to Watch</h2>
        <p className="text-xs text-slate-500 mb-2">
          Automatically push each day's workouts to your watch via intervals.icu at 5 AM.
        </p>
        <button
          onClick={() => update('auto_push', !profile.auto_push)}
          className={`flex items-center gap-3 p-3 rounded-xl w-full transition-colors ${
            profile.auto_push
              ? 'bg-success/10 border border-success/30'
              : 'bg-bg-tertiary border border-white/5 hover:bg-bg-hover'
          }`}
        >
          <div className={`w-10 h-6 rounded-full relative transition-colors ${
            profile.auto_push ? 'bg-success' : 'bg-slate-700'
          }`}>
            <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
              profile.auto_push ? 'left-5' : 'left-1'
            }`} />
          </div>
          <span className="text-sm">{profile.auto_push ? 'Enabled' : 'Disabled'}</span>
        </button>
      </div>

      <TrainingStyleToggle profile={profile} update={update} />

      <div>
        <label className="text-xs text-slate-400 block mb-1">Additional Notes</label>
        <textarea
          value={profile.notes}
          onChange={(e) => update('notes', e.target.value)}
          placeholder="Anything else the coach should know? Injuries, time constraints, preferences..."
          rows={3}
          className="w-full bg-bg-tertiary text-sm rounded-xl px-3 py-2.5 border border-white/5 placeholder:text-slate-600 resize-none"
        />
      </div>
    </div>
  )
}

/** Backend hard-enforces weekly_hours >= 12 and ramp-stability at generation
 *  time regardless of this toggle — the gate here is just steering the
 *  athlete before they hit a no-op, not the actual guard. */
function TrainingStyleToggle({ profile, update }: any) {
  const eligible = profile.weekly_hours >= 12 && profile.experience_level === 'advanced'
  const active = profile.training_style === 'norwegian'

  return (
    <div>
      <h2 className="text-sm font-medium mb-2">Training Style</h2>
      <p className="text-xs text-slate-500 mb-2">
        Norwegian-style double-threshold days, restructuring quality sessions into an AM/PM pair.
      </p>
      <button
        onClick={() => eligible && update('training_style', active ? 'standard' : 'norwegian')}
        disabled={!eligible}
        className={`flex items-center gap-3 p-3 rounded-xl w-full transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
          active
            ? 'bg-accent/15 border border-accent/30'
            : 'bg-bg-tertiary border border-white/5 hover:enabled:bg-bg-hover'
        }`}
      >
        <div className={`w-10 h-6 rounded-full relative transition-colors ${
          active ? 'bg-accent' : 'bg-slate-700'
        }`}>
          <div className={`absolute top-1 w-4 h-4 rounded-full bg-white transition-transform ${
            active ? 'left-5' : 'left-1'
          }`} />
        </div>
        <span className="text-sm">{active ? 'Norwegian' : 'Standard'}</span>
      </button>
      {!eligible && (
        <p className="text-[11px] text-warning mt-2">
          Needs 12+ weekly hours and Advanced experience — currently{' '}
          {profile.weekly_hours}h and {profile.experience_level || 'not set'}.
        </p>
      )}
    </div>
  )
}

function labelFor(value: string, items: { value: string; label: string }[]): string {
  return items.find((i) => i.value === value)?.label || value.replace(/_/g, ' ')
}

function labelsFor(values: string[], items: { value: string; label: string }[]): string {
  return values.map((v) => labelFor(v, items)).join(', ') || 'None specified'
}

/** "6 Cycling, 3 Running" for whichever disciplines were given a set count. */
function statedSessions(profile: any): string {
  const limits: Record<string, any> = profile.sport_limits || {}
  return SPORTS.filter((s) => profile.sports.includes(s.value) && limits[s.value]?.sessions)
    .map((s) => `${limits[s.value].sessions} ${s.label}`)
    .join(', ')
}

/** "Cycling → Saturday, Running → Sunday" for sports with a pinned long day. */
function statedLongDays(profile: any): string {
  const limits: Record<string, any> = profile.sport_limits || {}
  return SPORTS.filter((s) => profile.sports.includes(s.value) && limits[s.value]?.long_day)
    .map((s) => `${s.label} → ${limits[s.value].long_day.charAt(0).toUpperCase()}${limits[s.value].long_day.slice(1)}`)
    .join(', ')
}

/** Sports whose session count is locked (held flat rather than scaled during ramp/recovery weeks). */
function statedLocks(profile: any): string {
  const limits: Record<string, any> = profile.sport_limits || {}
  return SPORTS.filter((s) => profile.sports.includes(s.value) && limits[s.value]?.lock_sessions)
    .map((s) => s.label)
    .join(', ')
}

function StepReview({ profile, isGenerating, planStart, setPlanStart }: any) {
  const items = [
    { label: 'Experience', value: labelFor(profile.experience_level, EXPERIENCE_LEVELS) },
    { label: 'Sports', value: labelsFor(profile.sports, SPORTS) },
    { label: 'Goal', value: labelFor(profile.goal, GOALS) + (profile.goal_event ? ` (${profile.goal_event})` : '') },
    { label: 'Weaknesses', value: labelsFor(profile.weaknesses, ABILITIES) },
    { label: 'Strengths', value: labelsFor(profile.strengths, ABILITIES) },
    { label: 'Weekly Hours', value: `${profile.weekly_hours}h` },
    {
      label: 'Training Now',
      value: `${profile.current_weekly_hours ?? profile.weekly_hours}h — plan ramps toward ${profile.weekly_hours}h`,
    },
    {
      label: 'Volume Progression',
      value: profile.volume_progression_mode === 'steady' ? 'Steady (ramp-in, then hold)' : 'Ramp',
    },
    {
      label: 'Sessions/Day',
      value: profile.max_sessions_per_day >= 2
        ? `Up to ${profile.max_sessions_per_day}`
        : '1',
    },
    {
      label: 'Sessions/Sport',
      value: statedSessions(profile) || 'Auto — set from your weekly hours',
    },
    { label: 'Long Days', value: statedLongDays(profile) || 'Auto' },
    { label: 'Locked Counts', value: statedLocks(profile) || 'None' },
    { label: 'Hard Days', value: profile.preferred_hard_days.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1, 3)).join(', ') },
    { label: 'Rest Days', value: profile.preferred_rest_days.map((d: string) => d.charAt(0).toUpperCase() + d.slice(1, 3)).join(', ') },
    {
      label: 'Recovery Weeks',
      value: profile.recovery_mode === 'extended'
        ? `Extended${profile.recovery_cycle_weeks ? ` (every ${profile.recovery_cycle_weeks}w)` : ''}`
        : profile.recovery_mode === 'off' ? 'Off (until forced)' : 'Auto',
    },
    { label: 'Plan Duration', value: `${profile.plan_duration_weeks} weeks` },
    { label: 'Equipment', value: [
      profile.has_trainer && 'Trainer',
      profile.has_power_meter && 'Power Meter',
      profile.has_hr_monitor && 'HR Monitor',
    ].filter(Boolean).join(', ') || 'None' },
    { label: 'Auto-Push', value: profile.auto_push ? 'Daily at 5 AM' : 'Off' },
    { label: 'Training Style', value: profile.training_style === 'norwegian' ? 'Norwegian' : 'Standard' },
  ]

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Review Your Profile</h2>

      <div>
        <h3 className="text-sm font-medium mb-1">Start the plan</h3>
        <p className="text-xs text-slate-500 mb-2">
          Starting today gives a short first week — only the days that are left.
        </p>
        <div className="grid grid-cols-2 gap-2">
          {[
            { value: 'next_week', label: 'Next Monday', desc: 'A clean, full first week' },
            { value: 'this_week', label: 'Today', desc: 'Train the rest of this week' },
          ].map((option) => (
            <button
              key={option.value}
              onClick={() => setPlanStart?.(option.value)}
              className={`text-left px-3 py-2 rounded-xl border transition-colors ${
                planStart === option.value
                  ? 'border-accent/40 bg-accent/10'
                  : 'border-white/5 bg-bg-tertiary hover:bg-bg-hover'
              }`}
            >
              <span className="text-sm block">{option.label}</span>
              <span className="text-[11px] text-slate-500">{option.desc}</span>
            </button>
          ))}
        </div>
      </div>
      <p className="text-xs text-slate-500">
        Confirm your settings. The AI coach will build a {profile.plan_duration_weeks}-week periodized plan
        tailored to your profile.
      </p>

      <div className="space-y-1">
        {items.map((item) => (
          <div key={item.label} className="flex items-center justify-between py-2 border-b border-white/5">
            <span className="text-xs text-slate-500">{item.label}</span>
            <span className="text-sm font-medium">{item.value}</span>
          </div>
        ))}
      </div>

      {profile.notes && (
        <div className="p-3 rounded-xl bg-bg-tertiary text-xs text-slate-400">
          <span className="text-slate-500">Notes:</span> {profile.notes}
        </div>
      )}

      {isGenerating && (
        <div className="p-4 rounded-xl bg-accent/5 border border-accent/20 text-center">
          <Loader2 className="w-6 h-6 animate-spin text-accent mx-auto mb-2" />
          <p className="text-sm text-slate-300">Generating your personalized training plan...</p>
          <p className="text-xs text-slate-500 mt-1">This may take a moment</p>
        </div>
      )}
    </div>
  )
}
