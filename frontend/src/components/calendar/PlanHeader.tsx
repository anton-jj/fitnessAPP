import { useState } from 'react'
import type { UseMutationResult } from '@tanstack/react-query'
import { api } from '../../api/client'
import {
  CalendarDays, Loader2, Watch, UserCog, Trash2, AlertTriangle, TrendingUp, Activity,
} from 'lucide-react'

const WEEK_TYPE_COLORS: Record<string, string> = {
  build: 'bg-success/10 text-success',
  recovery: 'bg-info/10 text-info',
  taper: 'bg-sport-other/10 text-sport-other',
}

const VOLUME_SOURCE_LABEL: Record<string, string> = {
  observed: 'Starting point taken from your synced training over the last few weeks.',
  stated: 'Starting point taken from the current volume you entered.',
  default: 'No training history yet — starting from a conservative default.',
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

interface PlanHeaderProps {
  plan: any
  currentWeek: any | null
  compliance: any
  adapt: UseMutationResult<any, Error, void>
  pushWeek: UseMutationResult<any, Error, number | undefined>
  deletePlan: UseMutationResult<any, Error, number>
  onNewPlan: () => void
  onEditSetup: () => void
}

/** Plan-level context above the month grid: description/volume-ramp/readiness
 *  notes, compliance ("how it's going"), the adaptation banner, and
 *  week-scoped sync actions for whichever week `currentWeek` (the week
 *  containing the selected date) points at. */
export default function PlanHeader({
  plan, currentWeek, compliance, adapt, pushWeek, deletePlan, onNewPlan, onEditSetup,
}: PlanHeaderProps) {
  const [copiedFeed, setCopiedFeed] = useState(false)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3 min-w-0">
        <span className="text-xs text-slate-500 truncate">{plan.name}</span>
        <button
          onClick={onEditSetup}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200 border border-white/10 hover:border-white/20 rounded-lg px-2.5 py-1.5 transition-colors shrink-0"
        >
          <UserCog className="w-3.5 h-3.5" />
          Edit setup
        </button>
      </div>

      {/* Plan description and volume ramp are narrative context, not
         actionable — plain muted text with no card chrome so they read as
         secondary instead of competing with the actual plan data below. */}
      <div className="space-y-1.5">
        {plan.plan.description && (
          <p className="text-xs text-slate-500 leading-relaxed">
            {plan.plan.description}
          </p>
        )}
        {plan.plan.progression_assessment?.peak_hours && (
          <div className="flex items-start gap-2 text-xs text-slate-600">
            <TrendingUp className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" />
            <div>
              <span>
                Volume ramps{' '}
                <span className="text-slate-500">
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

      {/* Selected week header */}
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

      {/* Sync actions for the selected week / whole plan */}
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

      {/* Plan-level info and actions */}
      {plan.plan.progression_notes && (
        <p className="text-xs text-slate-600 italic px-0.5">
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
            onClick={onNewPlan}
            className="px-3 py-1.5 rounded-lg bg-bg-tertiary hover:bg-bg-hover transition-colors"
          >
            New Plan
          </button>
        </div>
      </div>
    </div>
  )
}
