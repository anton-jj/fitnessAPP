import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import StreamChart from '../components/StreamChart'
import StatCard from '../components/StatCard'
import { ArrowLeft, Clock, Ruler, Mountain, Heart, Zap, Gauge } from 'lucide-react'
import { format } from 'date-fns'

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  return `${m}:${s.toString().padStart(2, '0')}`
}

export default function ActivityDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const { data: activity, isLoading } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => api.activity(Number(id)),
    enabled: !!id,
  })

  if (isLoading) {
    return <div className="text-center text-slate-500 py-12">Loading...</div>
  }
  if (!activity) {
    return <div className="text-center text-slate-500 py-12">Activity not found</div>
  }

  const a = activity

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          className="p-2 rounded-lg bg-bg-secondary hover:bg-bg-hover transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
        </button>
        <div>
          <h1 className="text-lg font-bold">{a.name || 'Activity'}</h1>
          <div className="flex items-center gap-2 text-xs text-slate-400">
            {a.start_time && format(new Date(a.start_time), 'EEEE, MMMM d, yyyy · h:mm a')}
            {a.source && (
              <>
                <span className="text-slate-600">·</span>
                {a.source.split(',').map((s: string) => (
                  <span key={s} className="px-1.5 py-0.5 rounded bg-white/5 text-slate-500">
                    {s}
                  </span>
                ))}
              </>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {a.moving_time && (
          <StatCard
            label="Duration"
            value={formatDuration(a.moving_time)}
            icon={<Clock className="w-4 h-4" />}
          />
        )}
        {a.distance > 0 && (
          <StatCard
            label="Distance"
            value={`${(a.distance / 1000).toFixed(1)} km`}
            icon={<Ruler className="w-4 h-4" />}
          />
        )}
        {a.elevation_gain > 0 && (
          <StatCard
            label="Elevation"
            value={`${Math.round(a.elevation_gain)} m`}
            icon={<Mountain className="w-4 h-4" />}
          />
        )}
        {a.avg_hr > 0 && (
          <StatCard
            label="Avg HR"
            value={`${Math.round(a.avg_hr)}`}
            sub={a.max_hr ? `Max: ${Math.round(a.max_hr)}` : undefined}
            icon={<Heart className="w-4 h-4" />}
            color="text-danger"
          />
        )}
        {a.avg_power > 0 && (
          <StatCard
            label="Avg Power"
            value={`${Math.round(a.avg_power)} W`}
            sub={a.normalized_power ? `NP: ${Math.round(a.normalized_power)} W` : undefined}
            icon={<Zap className="w-4 h-4" />}
            color="text-warning"
          />
        )}
        {a.tss > 0 && (
          <StatCard
            label="TSS"
            value={Math.round(a.tss)}
            sub={a.intensity_factor ? `IF: ${a.intensity_factor.toFixed(2)}` : undefined}
            icon={<Gauge className="w-4 h-4" />}
            color="text-accent"
          />
        )}
        {a.avg_cadence > 0 && (
          <StatCard label="Avg Cadence" value={`${Math.round(a.avg_cadence)}`} sub="rpm" />
        )}
        {a.calories > 0 && (
          <StatCard label="Calories" value={Math.round(a.calories)} sub="kcal" />
        )}
      </div>

      {a.streams && <StreamChart streams={a.streams} />}

      {a.laps && a.laps.length > 0 && (
        <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
          <h2 className="text-sm font-medium text-slate-300 mb-3">Laps</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-white/5">
                  <th className="text-left py-2 px-2">#</th>
                  <th className="text-right py-2 px-2">Time</th>
                  <th className="text-right py-2 px-2">Dist</th>
                  <th className="text-right py-2 px-2">HR</th>
                  <th className="text-right py-2 px-2">Power</th>
                </tr>
              </thead>
              <tbody>
                {a.laps.map((lap: any, i: number) => (
                  <tr key={i} className="border-b border-white/5">
                    <td className="py-2 px-2 text-slate-400">{i + 1}</td>
                    <td className="text-right py-2 px-2">{lap.elapsed_time ? formatDuration(lap.elapsed_time) : '—'}</td>
                    <td className="text-right py-2 px-2">{lap.distance ? `${(lap.distance / 1000).toFixed(2)} km` : '—'}</td>
                    <td className="text-right py-2 px-2">{lap.average_heartrate ? Math.round(lap.average_heartrate) : '—'}</td>
                    <td className="text-right py-2 px-2">{lap.average_watts ? Math.round(lap.average_watts) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
