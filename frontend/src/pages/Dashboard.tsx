import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import FitnessChart from '../components/FitnessChart'
import VolumeChart from '../components/VolumeChart'
import ActivityCard from '../components/ActivityCard'
import { Clock, Zap, TrendingUp, Activity, RefreshCw } from 'lucide-react'

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['dashboard'], queryFn: () => api.dashboard() })
  const { data: volume } = useQuery({ queryKey: ['volume'], queryFn: () => api.volume() })
  const { mutate: sync, isPending: syncing } = useMutation({
    mutationFn: () => api.triggerSync(),
    onSuccess: () => {
      setTimeout(() => queryClient.invalidateQueries(), 5000)
    },
  })

  if (isLoading) {
    return <div className="flex items-center justify-center h-64 text-slate-500">Loading...</div>
  }

  const d = data || { fitness_data: [], weekly_summary: {}, recent_activities: [] }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Dashboard</h1>
        <button
          onClick={() => sync()}
          disabled={syncing}
          className="flex items-center gap-2 px-3 py-1.5 text-xs rounded-lg bg-bg-secondary border border-white/5 hover:bg-bg-hover transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : ''}`} />
          Sync
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="Week Hours"
          value={d.weekly_summary.hours || 0}
          icon={<Clock className="w-4 h-4" />}
        />
        <StatCard
          label="Week TSS"
          value={Math.round(d.weekly_summary.tss || 0)}
          icon={<Zap className="w-4 h-4" />}
          color="text-accent"
        />
        <StatCard
          label="Fitness (CTL)"
          value={d.current_ctl ? Math.round(d.current_ctl) : '—'}
          icon={<TrendingUp className="w-4 h-4" />}
          color="text-info"
        />
        <StatCard
          label="Form (TSB)"
          value={d.current_tsb ? Math.round(d.current_tsb) : '—'}
          sub={d.current_tsb ? (d.current_tsb > 0 ? 'Fresh' : d.current_tsb > -20 ? 'Optimal' : 'Fatigued') : undefined}
          icon={<Activity className="w-4 h-4" />}
          color={d.current_tsb && d.current_tsb > 0 ? 'text-success' : 'text-warning'}
        />
      </div>

      <FitnessChart data={d.fitness_data} />
      {volume && <VolumeChart data={volume} />}

      <div>
        <h2 className="text-sm font-medium text-slate-300 mb-3">Recent Activities</h2>
        <div className="space-y-2">
          {d.recent_activities.length > 0 ? (
            d.recent_activities.map((a: any) => (
              <ActivityCard key={a.id} activity={a} />
            ))
          ) : (
            <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
              No activities yet. Connect Strava or intervals.icu in Settings and sync.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
