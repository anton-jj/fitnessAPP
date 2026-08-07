import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api } from '../api/client'
import {
  format, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
  eachDayOfInterval, isSameMonth, isToday, addMonths, subMonths,
} from 'date-fns'
import { ChevronLeft, ChevronRight, AlertTriangle, GripVertical } from 'lucide-react'

const sportColors: Record<string, string> = {
  running: 'bg-sport-running',
  cycling: 'bg-sport-cycling',
  swimming: 'bg-sport-swimming',
  strength: 'bg-sport-strength',
}

const DAY_NAMES = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']

function getDayName(date: Date): string {
  return DAY_NAMES[(date.getDay() + 6) % 7]
}

export default function Calendar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [currentMonth, setCurrentMonth] = useState(new Date())
  const [dragItem, setDragItem] = useState<{
    dateKey: string; index: number; workout: any
  } | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)
  const [advice, setAdvice] = useState<string | null>(null)

  const year = currentMonth.getFullYear()
  const month = currentMonth.getMonth() + 1

  const { data: calendarData = {} } = useQuery({
    queryKey: ['calendar', year, month],
    queryFn: () => api.calendar(year, month),
  })

  const { data: currentPlan } = useQuery({
    queryKey: ['plan'],
    queryFn: () => api.currentPlan(),
  })

  const moveMutation = useMutation({
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

  const findPlanWeek = useCallback((dateKey: string): { planId: number; weekNumber: number } | null => {
    if (!currentPlan?.id || !currentPlan?.plan) return null

    const weeks = currentPlan.plan.weeks || []
    for (const w of weeks) {
      for (const d of w.days || []) {
        if (d.date === dateKey) {
          return { planId: currentPlan.id, weekNumber: w.week_number }
        }
      }
    }

    if (currentPlan.plan.days) {
      for (const d of currentPlan.plan.days) {
        if (d.date === dateKey) {
          return { planId: currentPlan.id, weekNumber: 1 }
        }
      }
    }
    return null
  }, [currentPlan])

  const handleDragStart = (dateKey: string, index: number, workout: any) => {
    setDragItem({ dateKey, index, workout })
  }

  const handleDragOver = (e: React.DragEvent, dateKey: string) => {
    e.preventDefault()
    setDropTarget(dateKey)
  }

  const handleDragLeave = () => {
    setDropTarget(null)
  }

  const handleDrop = (e: React.DragEvent, toDateKey: string) => {
    e.preventDefault()
    setDropTarget(null)

    if (!dragItem || dragItem.dateKey === toDateKey) {
      setDragItem(null)
      return
    }

    const fromDate = new Date(dragItem.dateKey)
    const toDate = new Date(toDateKey)
    const planInfo = findPlanWeek(dragItem.dateKey)

    if (!planInfo) {
      setDragItem(null)
      return
    }

    const toWeekInfo = findPlanWeek(toDateKey)
    if (!toWeekInfo || toWeekInfo.weekNumber !== planInfo.weekNumber) {
      setAdvice('Can only move workouts within the same week')
      setTimeout(() => setAdvice(null), 4000)
      setDragItem(null)
      return
    }

    const plannedBefore = (calendarData[dragItem.dateKey] || [])
      .filter((a: any) => a.planned)
    const fromIndex = plannedBefore.findIndex((_: any, i: number) => {
      const allItems = calendarData[dragItem.dateKey] || []
      const plannedIdx = allItems.filter((a: any) => a.planned).indexOf(plannedBefore[i])
      return i === dragItem.index
    })

    moveMutation.mutate({
      plan_id: planInfo.planId,
      week_number: planInfo.weekNumber,
      from_day: getDayName(fromDate),
      from_index: dragItem.index,
      to_day: getDayName(toDate),
    })

    setDragItem(null)
  }

  const monthStart = startOfMonth(currentMonth)
  const monthEnd = endOfMonth(currentMonth)
  const calStart = startOfWeek(monthStart, { weekStartsOn: 1 })
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
  const days = eachDayOfInterval({ start: calStart, end: calEnd })

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Calendar</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setCurrentMonth(subMonths(currentMonth, 1))}
            className="p-1.5 rounded-lg bg-bg-secondary hover:bg-bg-hover transition-colors"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-sm font-medium min-w-[120px] text-center">
            {format(currentMonth, 'MMMM yyyy')}
          </span>
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

      <div className="bg-bg-secondary rounded-xl border border-white/5 overflow-hidden">
        <div className="grid grid-cols-7 text-xs text-slate-500 border-b border-white/5">
          {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
            <div key={d} className="py-2 text-center font-medium">{d}</div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {days.map((day) => {
            const dateKey = format(day, 'yyyy-MM-dd')
            const dayActivities = calendarData[dateKey] || []
            const inMonth = isSameMonth(day, currentMonth)
            const today = isToday(day)
            const isDropping = dropTarget === dateKey

            return (
              <div
                key={dateKey}
                onDragOver={(e) => handleDragOver(e, dateKey)}
                onDragLeave={handleDragLeave}
                onDrop={(e) => handleDrop(e, dateKey)}
                className={`min-h-[80px] md:min-h-[100px] p-1.5 border-b border-r border-white/5 transition-colors ${
                  !inMonth ? 'opacity-30' : ''
                } ${today ? 'bg-accent/5' : ''} ${
                  isDropping ? 'bg-accent/10 ring-1 ring-accent/30 ring-inset' : ''
                }`}
              >
                <div className={`text-xs mb-1 ${today ? 'text-accent font-bold' : 'text-slate-500'}`}>
                  {format(day, 'd')}
                </div>
                <div className="space-y-0.5">
                  {dayActivities.slice(0, 4).map((a: any, i: number) => {
                    const isPlanned = a.planned
                    const plannedItems = dayActivities.filter((x: any) => x.planned)
                    const plannedIndex = isPlanned ? plannedItems.indexOf(a) : -1

                    return (
                      <div
                        key={i}
                        draggable={isPlanned}
                        onDragStart={() => isPlanned && handleDragStart(dateKey, plannedIndex, a)}
                        onClick={() => a.id && navigate(`/activities/${a.id}`)}
                        className={`text-[10px] px-1 py-0.5 rounded truncate transition-colors flex items-center gap-0.5 ${
                          isPlanned
                            ? 'border border-dashed border-white/10 bg-white/[0.02] text-slate-400 cursor-grab active:cursor-grabbing hover:border-accent/30'
                            : 'cursor-pointer bg-bg-hover hover:bg-bg-tertiary text-slate-300'
                        }`}
                      >
                        {isPlanned && (
                          <GripVertical className="w-2.5 h-2.5 opacity-30 flex-shrink-0" />
                        )}
                        {/* The dashed border already says "planned" — let the dot
                            carry the sport so a month reads at a glance. */}
                        <span
                          className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                            sportColors[a.sport_type] || 'bg-sport-other'
                          }`}
                        />
                        <span className="hidden md:inline truncate ml-0.5">{a.name || a.sport_type}</span>
                        <span className="md:hidden ml-0.5">{a.sport_type?.slice(0, 3)}</span>
                      </div>
                    )
                  })}
                  {dayActivities.length > 4 && (
                    <div className="text-[10px] text-slate-500 px-1">
                      +{dayActivities.length - 4} more
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {moveMutation.isPending && (
        <p className="text-xs text-slate-500 text-center">Moving workout...</p>
      )}
      {moveMutation.isError && (
        <p className="text-xs text-danger text-center">Failed to move workout. Only planned workouts within the same week can be moved.</p>
      )}
    </div>
  )
}
