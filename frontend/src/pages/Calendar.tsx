import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import { format, addMonths, subMonths } from 'date-fns'
import { ChevronLeft, ChevronRight, AlertTriangle, CalendarDays } from 'lucide-react'
import QuickPlanCta from '../components/calendar/QuickPlanCta'
import PlanHeader from '../components/calendar/PlanHeader'
import MonthGrid from '../components/calendar/MonthGrid'
import DayDetailPanel from '../components/calendar/DayDetailPanel'

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

interface PlannedDay {
  weekNumber: number
  dayName: string
  workouts: any[]
}

function hasNonRestWorkout(pd?: PlannedDay): boolean {
  return Boolean(pd?.workouts?.some((w: any) => w.workout_type !== 'rest'))
}

export default function Calendar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [selectedDate, setSelectedDate] = useState<string>(() => format(new Date(), 'yyyy-MM-dd'))
  const [swapSource, setSwapSource] = useState<{ date: string; index: number } | null>(null)
  const [advice, setAdvice] = useState<string | null>(null)
  const autoSelectedRef = useRef(false)

  const year = currentMonth.getFullYear()
  const month = currentMonth.getMonth() + 1

  const { data: plan, isLoading: planLoading } = useQuery({
    queryKey: ['plan'],
    queryFn: () => api.currentPlan(),
  })

  const { data: calendarData = {}, isLoading: calendarLoading } = useQuery({
    queryKey: ['calendar', year, month],
    queryFn: () => api.calendar(year, month),
  })

  const { data: compliance } = useQuery({
    queryKey: ['compliance', plan?.id],
    queryFn: () => api.planCompliance(plan.id),
    enabled: Boolean(plan?.id),
  })

  const hasPlan = Boolean(plan && plan.plan)
  const weeks = useMemo(() => (hasPlan ? getWeeks(plan.plan) : []), [hasPlan, plan])

  const plannedByDate = useMemo(() => {
    const map: Record<string, PlannedDay> = {}
    for (const w of weeks) {
      for (const d of w.days || []) {
        if (!d.date) continue
        map[d.date] = {
          weekNumber: w.week_number,
          dayName: (d.day || '').toLowerCase(),
          // A rest day is stored as an explicit workout_type "rest"
          // placeholder, not an empty array — filter it out here so
          // downstream consumers (grid chip count, swap eligibility, day
          // panel) never treat "rest" as a real, swappable session.
          workouts: (d.workouts || []).filter((w: any) => w.workout_type !== 'rest'),
        }
      }
    }
    return map
  }, [weeks])

  const currentWeek = useMemo(() => {
    const wn = plannedByDate[selectedDate]?.weekNumber
    if (wn == null) return null
    return weeks.find((w: any) => w.week_number === wn) ?? null
  }, [plannedByDate, selectedDate, weeks])

  // Default the selected date to today if there's anything to see there;
  // otherwise land on the nearest upcoming planned workout so the panel
  // doesn't open empty. Runs once, after both queries have settled.
  useEffect(() => {
    if (autoSelectedRef.current) return
    if (planLoading || calendarLoading) return
    autoSelectedRef.current = true
    const todayKey = format(new Date(), 'yyyy-MM-dd')
    const hasToday = hasNonRestWorkout(plannedByDate[todayKey]) || (calendarData[todayKey] || []).length > 0
    if (!hasToday) {
      const upcoming = Object.keys(plannedByDate)
        .filter((k) => k >= todayKey && hasNonRestWorkout(plannedByDate[k]))
        .sort()[0]
      if (upcoming) setSelectedDate(upcoming)
    }
  }, [planLoading, calendarLoading, plannedByDate, calendarData])

  const adjust = useMutation({
    mutationFn: ({ action, details, week_number }: { action: string; details: string; week_number?: number }) =>
      api.adjustPlan(plan.id, action, details, week_number),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plan'] }),
  })

  // Swapping two workouts is a pure data move — no AI judgment call needed —
  // so it applies instantly against the local cache and persists deterministically
  // in the background, instead of paying for a slow full-week AI rewrite.
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

  const moveWorkout = useMutation({
    mutationFn: (data: { plan_id: number; week_number: number; from_day: string; from_index: number; to_day: string }) =>
      api.moveWorkout(data),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['calendar'] })
      queryClient.invalidateQueries({ queryKey: ['plan'] })
      if (result.advice) {
        setAdvice(result.advice)
        setTimeout(() => setAdvice(null), 8000)
      }
    },
  })

  const pushToWatch = useMutation({
    mutationFn: ({ workout, date }: { workout: any; date: string }) =>
      api.pushToWatch(workout, date),
  })

  const pushWeek = useMutation({
    mutationFn: (weekNumber?: number) => api.pushPlan(plan.id, weekNumber),
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
    },
  })

  const completeSwap = useCallback((targetDate: string, targetIndex: number) => {
    if (!swapSource) return
    const sourceInfo = plannedByDate[swapSource.date]
    const targetInfo = plannedByDate[targetDate]
    if (!sourceInfo || !targetInfo) {
      setSwapSource(null)
      return
    }
    if (sourceInfo.weekNumber !== targetInfo.weekNumber) {
      setAdvice('Can only swap workouts within the same week')
      setTimeout(() => setAdvice(null), 4000)
      setSwapSource(null)
      return
    }
    swapWorkout.mutate({
      week_number: sourceInfo.weekNumber,
      day_a: sourceInfo.dayName,
      index_a: swapSource.index,
      day_b: targetInfo.dayName,
      index_b: targetIndex,
    })
    setSwapSource(null)
  }, [swapSource, plannedByDate, swapWorkout])

  const handleDropWorkout = useCallback((fromDate: string, fromIndex: number, toDate: string) => {
    if (!plan?.id) return
    const fromInfo = plannedByDate[fromDate]
    const toInfo = plannedByDate[toDate]
    if (!fromInfo) return
    if (!toInfo || toInfo.weekNumber !== fromInfo.weekNumber) {
      setAdvice('Can only move workouts within the same week')
      setTimeout(() => setAdvice(null), 4000)
      return
    }
    moveWorkout.mutate({
      plan_id: plan.id,
      week_number: fromInfo.weekNumber,
      from_day: fromInfo.dayName,
      from_index: fromIndex,
      to_day: toInfo.dayName,
    })
  }, [plan, plannedByDate, moveWorkout])

  const toggleSwapSource = (index: number) => {
    if (swapSource && swapSource.date === selectedDate && swapSource.index === index) {
      setSwapSource(null)
    } else {
      setSwapSource({ date: selectedDate, index })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold flex items-center gap-2">
          <CalendarDays className="w-5 h-5 text-accent" /> Calendar
        </h1>
      </div>

      {planLoading ? (
        <div className="flex items-center justify-center h-64 text-slate-500">Loading...</div>
      ) : (
        <>
          {!hasPlan && <QuickPlanCta />}

          {hasPlan && (
            <PlanHeader
              plan={plan}
              currentWeek={currentWeek}
              compliance={compliance}
              adapt={adapt}
              pushWeek={pushWeek}
              deletePlan={deletePlan}
              onNewPlan={() => queryClient.setQueryData(['plan'], null)}
              onEditSetup={() => navigate('/onboarding')}
            />
          )}

          {/* Below lg, the day panel stacks under the grid (works fine at
             mobile width); at lg+ there's room to run it as a side panel
             next to the grid, TrainingPeaks-style, instead of a long single
             column that makes the day's detail a full scroll away. */}
          <div className="lg:flex lg:items-start lg:gap-4">
            <div className="lg:flex-1 lg:min-w-0 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{format(currentMonth, 'MMMM yyyy')}</span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
                    className="p-1.5 rounded-lg bg-bg-secondary hover:bg-bg-hover transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setCurrentMonth(addMonths(currentMonth, 1))}
                    className="p-1.5 rounded-lg bg-bg-secondary hover:bg-bg-hover transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {advice && (
                <div className="flex items-start gap-2 bg-accent/10 border border-accent/20 rounded-xl p-3 text-sm text-accent">
                  <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
                  <span>{advice}</span>
                </div>
              )}

              {calendarLoading ? (
                <div className="flex items-center justify-center h-32 text-slate-500">Loading calendar...</div>
              ) : (
                <MonthGrid
                  currentMonth={currentMonth}
                  calendarData={calendarData}
                  plannedByDate={plannedByDate}
                  selectedDate={selectedDate}
                  onSelectDate={setSelectedDate}
                  swapSource={swapSource}
                  onCompleteSwap={completeSwap}
                  onDropWorkout={handleDropWorkout}
                />
              )}

              {moveWorkout.isPending && (
                <p className="text-xs text-slate-500 text-center">Moving workout...</p>
              )}
              {moveWorkout.isError && (
                <p className="text-xs text-danger text-center">Failed to move workout. Only planned workouts within the same week can be moved.</p>
              )}
            </div>

            <div className="mt-4 lg:mt-0 lg:w-[22rem] lg:flex-shrink-0 lg:sticky lg:top-4 lg:self-start">
              <DayDetailPanel
                date={selectedDate}
                displayDate={format(new Date(`${selectedDate}T00:00:00`), 'EEEE, MMM d')}
                dayInfo={plannedByDate[selectedDate] ?? null}
                activities={calendarData[selectedDate] || []}
                swapActive={swapSource != null}
                swapSourceIndex={swapSource && swapSource.date === selectedDate ? swapSource.index : null}
                onToggleSwapSource={toggleSwapSource}
                onSwapTargetClick={(index) => completeSwap(selectedDate, index)}
                adjust={adjust}
                pushToWatch={pushToWatch}
              />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
