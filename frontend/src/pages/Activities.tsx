import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import ActivityCard from '../components/ActivityCard'
import { Filter } from 'lucide-react'

const SPORTS = ['all', 'running', 'cycling', 'swimming', 'strength', 'hiking', 'xcski']

export default function Activities() {
  const [sport, setSport] = useState('all')
  const [days, setDays] = useState(90)

  const { data: activities = [], isLoading } = useQuery({
    queryKey: ['activities', sport, days],
    queryFn: () => api.activities({ sport: sport === 'all' ? undefined : sport, days, limit: 100 }),
  })

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Activities</h1>

      <div className="flex flex-wrap gap-2 items-center">
        <Filter className="w-4 h-4 text-slate-500" />
        {SPORTS.map((s) => (
          <button
            key={s}
            onClick={() => setSport(s)}
            className={`px-3 py-1 text-xs rounded-full transition-colors ${
              sport === s
                ? 'bg-accent text-bg-primary'
                : 'bg-bg-secondary text-slate-400 hover:bg-bg-hover'
            }`}
          >
            {s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        <div className="ml-auto">
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="bg-bg-secondary text-slate-300 text-xs rounded-lg px-2 py-1 border border-white/5"
          >
            <option value={30}>30 days</option>
            <option value={90}>90 days</option>
            <option value={180}>6 months</option>
            <option value={365}>1 year</option>
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="text-center text-slate-500 py-12">Loading...</div>
      ) : activities.length === 0 ? (
        <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
          No activities found.
        </div>
      ) : (
        <div className="space-y-2">
          {activities.map((a: any) => (
            <ActivityCard key={a.id} activity={a} />
          ))}
        </div>
      )}
    </div>
  )
}
