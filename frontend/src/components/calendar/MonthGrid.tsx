import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  format, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
  eachDayOfInterval, isSameMonth, isToday,
} from 'date-fns'
import { GripVertical } from 'lucide-react'
import {
  SPORT_DOT_CLASS, SPORT_DOT_FALLBACK,
  SPORT_BADGE_CLASS, SPORT_BADGE_FALLBACK,
  SPORT_PLANNED_CLASS, SPORT_PLANNED_FALLBACK,
} from '../../lib/sport'

interface PlannedDay {
  weekNumber: number
  dayName: string
  workouts: any[]
}

interface MonthGridProps {
  currentMonth: Date
  calendarData: Record<string, any[]>
  plannedByDate: Record<string, PlannedDay>
  selectedDate: string
  onSelectDate: (dateKey: string) => void
  swapSource: { date: string; index: number } | null
  onCompleteSwap: (targetDate: string, targetIndex: number) => void
  onDropWorkout: (fromDate: string, fromIndex: number, toDate: string) => void
}

/** Month grid: sport dots for real synced activities, plus a dashed
 *  draggable chip per planned (not-yet-happened) workout, sourced from
 *  `plannedByDate` (derived from the current plan) rather than the removed
 *  calendar-endpoint stub. Extracted from the old Calendar.tsx page. */
export default function MonthGrid({
  currentMonth, calendarData, plannedByDate, selectedDate, onSelectDate,
  swapSource, onCompleteSwap, onDropWorkout,
}: MonthGridProps) {
  const navigate = useNavigate()
  const [dragItem, setDragItem] = useState<{ dateKey: string; index: number } | null>(null)
  const [dropTarget, setDropTarget] = useState<string | null>(null)

  const handleDragStart = (dateKey: string, index: number) => {
    setDragItem({ dateKey, index })
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
    onDropWorkout(dragItem.dateKey, dragItem.index, toDateKey)
    setDragItem(null)
  }

  const monthStart = startOfMonth(currentMonth)
  const monthEnd = endOfMonth(currentMonth)
  const calStart = startOfWeek(monthStart, { weekStartsOn: 1 })
  const calEnd = endOfWeek(monthEnd, { weekStartsOn: 1 })
  const days = eachDayOfInterval({ start: calStart, end: calEnd })
  const weekRows: Date[][] = []
  for (let i = 0; i < days.length; i += 7) weekRows.push(days.slice(i, i + 7))

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 overflow-hidden">
      <div className="grid grid-cols-[repeat(7,minmax(0,1fr))_auto] text-xs text-slate-500 border-b border-white/5">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
          <div key={d} className="py-2 text-center font-medium">{d}</div>
        ))}
        <div className="py-2 px-3 text-right font-medium">Week</div>
      </div>
      {weekRows.map((week) => {
        // TrainingPeaks-style weekly rollup: planned vs. completed hours/TSS
        // for the seven days in this row, so progress toward the week's
        // target is visible without opening the plan header.
        let plannedMin = 0, plannedTss = 0, doneMin = 0, doneTss = 0
        for (const day of week) {
          const dateKey = format(day, 'yyyy-MM-dd')
          for (const w of plannedByDate[dateKey]?.workouts || []) {
            plannedMin += w.duration_minutes || 0
            plannedTss += w.tss_estimate || 0
          }
          for (const a of calendarData[dateKey] || []) {
            doneMin += (a.moving_time || a.elapsed_time || 0) / 60
            doneTss += a.tss || 0
          }
        }
        const hasWeekData = plannedMin > 0 || doneMin > 0

        return (
        <div key={week[0].toISOString()} className="grid grid-cols-[repeat(7,minmax(0,1fr))_auto]">
        {week.map((day) => {
          const dateKey = format(day, 'yyyy-MM-dd')
          const realActivities: any[] = calendarData[dateKey] || []
          const planned = plannedByDate[dateKey]
          const plannedWorkouts: any[] = planned?.workouts || []
          const inMonth = isSameMonth(day, currentMonth)
          const today = isToday(day)
          const isDropping = dropTarget === dateKey
          const isSelected = selectedDate === dateKey
          const isSwapEligible =
            swapSource != null && swapSource.date !== dateKey && plannedWorkouts.length === 1

          const totalItems = realActivities.length + plannedWorkouts.length
          const shownReal = realActivities.slice(0, 4)
          const shownPlanned = plannedWorkouts.slice(0, Math.max(0, 4 - shownReal.length))
          const overflow = totalItems - shownReal.length - shownPlanned.length

          return (
            <div
              key={dateKey}
              onDragOver={(e) => handleDragOver(e, dateKey)}
              onDragLeave={handleDragLeave}
              onDrop={(e) => handleDrop(e, dateKey)}
              onClick={() => {
                if (isSwapEligible) {
                  onCompleteSwap(dateKey, 0)
                } else {
                  onSelectDate(dateKey)
                }
              }}
              className={`min-h-[80px] md:min-h-[100px] min-w-0 p-1.5 border-b border-r border-white/5 transition-colors cursor-pointer overflow-hidden ${
                !inMonth ? 'opacity-30' : ''
              } ${today ? 'bg-accent/5' : ''} ${
                isSelected ? 'ring-1 ring-inset ring-accent/40' : ''
              } ${isDropping ? 'bg-accent/10 ring-1 ring-accent/30 ring-inset' : ''} ${
                isSwapEligible ? 'ring-1 ring-inset ring-accent/50' : ''
              }`}
            >
              <div className={`text-xs mb-1 ${today ? 'text-accent font-bold' : 'text-slate-500'}`}>
                {format(day, 'd')}
              </div>
              <div className="space-y-0.5">
                {shownReal.map((a: any) => (
                  <div
                    key={a.id}
                    onClick={(e) => {
                      e.stopPropagation()
                      if (a.id) navigate(`/activities/${a.id}`)
                    }}
                    className={`text-[10px] px-1 py-0.5 rounded truncate transition-colors flex items-center gap-0.5 cursor-pointer hover:brightness-125 ${
                      SPORT_BADGE_CLASS[a.sport_type] || SPORT_BADGE_FALLBACK
                    }`}
                  >
                    <span
                      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        SPORT_DOT_CLASS[a.sport_type] || SPORT_DOT_FALLBACK
                      }`}
                    />
                    <span className="hidden md:inline truncate min-w-0 ml-0.5">{a.name || a.sport_type}</span>
                    <span className="md:hidden ml-0.5">{a.sport_type?.slice(0, 3)}</span>
                  </div>
                ))}
                {shownPlanned.map((w: any, i: number) => (
                  <div
                    key={`planned-${i}`}
                    draggable
                    onDragStart={(e) => {
                      e.stopPropagation()
                      handleDragStart(dateKey, i)
                    }}
                    onClick={(e) => e.stopPropagation()}
                    className={`text-[10px] px-1 py-0.5 rounded truncate transition-colors flex items-center gap-0.5 border border-dashed cursor-grab active:cursor-grabbing hover:brightness-125 ${
                      SPORT_PLANNED_CLASS[w.sport] || SPORT_PLANNED_FALLBACK
                    }`}
                  >
                    <GripVertical className="w-2.5 h-2.5 opacity-40 flex-shrink-0" />
                    <span className="hidden md:inline truncate min-w-0 ml-0.5">{w.name || w.sport}</span>
                    <span className="md:hidden ml-0.5">{w.sport?.slice(0, 3)}</span>
                  </div>
                ))}
                {overflow > 0 && (
                  <div className="text-[10px] text-slate-500 px-1">
                    +{overflow} more
                  </div>
                )}
              </div>
            </div>
          )
        })}
        <div className="min-h-[80px] md:min-h-[100px] w-14 md:w-20 p-2 border-b border-l border-white/5 bg-white/[0.015] flex flex-col items-end justify-center gap-1 text-right flex-shrink-0">
          {hasWeekData ? (
            <>
              <span className="text-xs tabular text-slate-300">
                {(doneMin / 60).toFixed(1)}<span className="text-slate-600">/{(plannedMin / 60).toFixed(1)}h</span>
              </span>
              <span className="text-[10px] tabular text-slate-500">
                {Math.round(doneTss)}<span className="text-slate-700">/{Math.round(plannedTss)} TSS</span>
              </span>
            </>
          ) : (
            <span className="text-[10px] text-slate-700">—</span>
          )}
        </div>
        </div>
        )
      })}
    </div>
  )
}
