import { useNavigate } from 'react-router-dom'
import { format } from 'date-fns'

const sportColors: Record<string, string> = {
  running: 'bg-sport-running/20 text-sport-running',
  cycling: 'bg-sport-cycling/20 text-sport-cycling',
  swimming: 'bg-sport-swimming/20 text-sport-swimming',
  strength: 'bg-sport-strength/20 text-sport-strength',
}

const sportIcons: Record<string, string> = {
  running: '🏃',
  cycling: '🚴',
  swimming: '🏊',
  strength: '🏋️',
  hiking: '🥾',
  xcski: '⛷️',
  rowing: '🚣',
  yoga: '🧘',
}

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function formatDistance(meters: number): string {
  if (meters >= 1000) return `${(meters / 1000).toFixed(1)} km`
  return `${Math.round(meters)} m`
}

function formatPace(minPerKm: number): string {
  const mins = Math.floor(minPerKm)
  const secs = Math.round((minPerKm - mins) * 60)
  return `${mins}:${secs.toString().padStart(2, '0')} /km`
}

interface Props {
  activity: any
  compact?: boolean
}

export default function ActivityCard({ activity, compact }: Props) {
  const navigate = useNavigate()
  const sport = activity.sport_type || 'other'
  const colorClass = sportColors[sport] || 'bg-sport-other/20 text-sport-other'
  const icon = sportIcons[sport] || '🏃'

  return (
    <div
      onClick={() => navigate(`/activities/${activity.id}`)}
      className="bg-bg-secondary rounded-xl p-4 border border-white/5 hover:border-white/10 cursor-pointer transition-all hover:bg-bg-hover"
    >
      <div className="flex items-start gap-3">
        <div className={`w-10 h-10 rounded-lg flex items-center justify-center text-lg ${colorClass}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h3 className="font-medium text-sm truncate min-w-0">{activity.name || 'Activity'}</h3>
            {activity.start_time && (
              <span className="text-xs text-slate-500 ml-2 whitespace-nowrap">
                {format(new Date(activity.start_time), compact ? 'MMM d' : 'EEE, MMM d')}
              </span>
            )}
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-0.5 mt-1.5 text-xs text-slate-400">
            {activity.moving_time && (
              <span className="whitespace-nowrap">{formatDuration(activity.moving_time)}</span>
            )}
            {activity.distance > 0 && (
              <span className="whitespace-nowrap">{formatDistance(activity.distance)}</span>
            )}
            {activity.avg_hr > 0 && <span className="whitespace-nowrap">{Math.round(activity.avg_hr)} bpm</span>}
            {activity.avg_power > 0 && <span className="whitespace-nowrap">{Math.round(activity.avg_power)} W</span>}
            {activity.avg_pace > 0 && sport === 'running' && (
              <span className="whitespace-nowrap">{formatPace(activity.avg_pace)}</span>
            )}
            {activity.tss > 0 && (
              <span className="text-accent whitespace-nowrap">{Math.round(activity.tss)} TSS</span>
            )}
          </div>
          {!compact && activity.source && (
            <div className="flex gap-1 mt-2">
              {activity.source.split(',').map((s: string) => (
                <span key={s} className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">
                  {s}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
