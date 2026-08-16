import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  format, startOfMonth, endOfMonth, startOfWeek, endOfWeek,
  eachDayOfInterval, isSameMonth, isToday,
} from 'date-fns'
import { GripVertical } from 'lucide-react'
import { SPORT_DOT_CLASS, SPORT_DOT_FALLBACK } from '../../lib/sport'

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

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 overflow-hidden">
      <div className="grid grid-cols-7 text-xs text-slate-500 border-b border-white/5">
        {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d) => (
          <div key={d} className="py-2 text-center font-medium">{d}</div>
        ))}
      </div>
      <div className="grid grid-cols-7">
        {days.map((day) => {
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
              className={`min-h-[80px] md:min-h-[100px] p-1.5 border-b border-r border-white/5 transition-colors cursor-pointer ${
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
                    className="text-[10px] px-1 py-0.5 rounded truncate transition-colors flex items-center gap-0.5 cursor-pointer bg-bg-hover hover:bg-bg-tertiary text-slate-300"
                  >
                    <span
                      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        SPORT_DOT_CLASS[a.sport_type] || SPORT_DOT_FALLBACK
                      }`}
                    />
                    <span className="hidden md:inline truncate ml-0.5">{a.name || a.sport_type}</span>
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
                    className="text-[10px] px-1 py-0.5 rounded truncate transition-colors flex items-center gap-0.5 border border-dashed border-white/10 bg-white/[0.02] text-slate-400 cursor-grab active:cursor-grabbing hover:border-accent/30"
                  >
                    <GripVertical className="w-2.5 h-2.5 opacity-30 flex-shrink-0" />
                    {/* The dashed border already says "planned" — let the dot
                        carry the sport so a month reads at a glance. */}
                    <span
                      className={`inline-block w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        SPORT_DOT_CLASS[w.sport] || SPORT_DOT_FALLBACK
                      }`}
                    />
                    <span className="hidden md:inline truncate ml-0.5">{w.name || w.sport}</span>
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
      </div>
    </div>
  )
}
