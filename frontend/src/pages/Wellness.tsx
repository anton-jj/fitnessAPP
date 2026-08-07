import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import { Heart, Moon, Scale, Brain } from 'lucide-react'
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip,
} from 'recharts'
import { format, parseISO } from 'date-fns'

export default function Wellness() {
  const [days, setDays] = useState(30)
  const { data: wellness = [] } = useQuery({
    queryKey: ['wellness', days],
    queryFn: () => api.wellness(days),
  })

  const latest = wellness.length > 0 ? wellness[wellness.length - 1] : null

  const chartData = wellness.map((w: any) => ({
    date: w.date,
    hrv: w.hrv,
    resting_hr: w.resting_hr,
    sleep: w.sleep_hours,
    weight: w.weight,
  }))

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Wellness</h1>
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          className="bg-bg-secondary text-slate-300 text-xs rounded-lg px-2 py-1 border border-white/5"
        >
          <option value={14}>2 weeks</option>
          <option value={30}>30 days</option>
          <option value={60}>60 days</option>
          <option value={90}>90 days</option>
        </select>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard
          label="HRV"
          value={latest?.hrv ? Math.round(latest.hrv) : '—'}
          sub="ms"
          icon={<Brain className="w-4 h-4" />}
          color="text-sport-other"
        />
        <StatCard
          label="Resting HR"
          value={latest?.resting_hr ? Math.round(latest.resting_hr) : '—'}
          sub="bpm"
          icon={<Heart className="w-4 h-4" />}
          color="text-danger"
        />
        <StatCard
          label="Sleep"
          value={latest?.sleep_hours ? `${latest.sleep_hours}h` : '—'}
          icon={<Moon className="w-4 h-4" />}
          color="text-info"
        />
        <StatCard
          label="Weight"
          value={latest?.weight ? `${latest.weight}` : '—'}
          sub="kg"
          icon={<Scale className="w-4 h-4" />}
        />
      </div>

      <WellnessChart data={chartData} dataKey="hrv" label="HRV" color="#9b8fa8" unit="ms" />
      <WellnessChart data={chartData} dataKey="resting_hr" label="Resting Heart Rate" color="#c07a72" unit="bpm" />
      <WellnessChart data={chartData} dataKey="sleep" label="Sleep Duration" color="#7d95ab" unit="hours" />
      <WellnessChart data={chartData} dataKey="weight" label="Weight" color="#8a97a3" unit="kg" />
    </div>
  )
}

function WellnessChart({ data, dataKey, label, color, unit }: {
  data: any[]; dataKey: string; label: string; color: string; unit: string
}) {
  const filtered = data.filter((d) => d[dataKey] != null)
  if (filtered.length === 0) return null

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
      <h2 className="text-sm font-medium text-slate-300 mb-3">{label}</h2>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={filtered} margin={{ top: 5, right: 5, bottom: 5, left: -10 }}>
          <XAxis
            dataKey="date"
            tickFormatter={(d) => { try { return format(parseISO(d), 'MMM d') } catch { return d } }}
            tick={{ fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis tick={{ fontSize: 11 }} domain={['dataMin - 2', 'dataMax + 2']} />
          <Tooltip
            contentStyle={{
              background: '#1f1e1c',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(d) => { try { return format(parseISO(d as string), 'EEE, MMM d') } catch { return d } }}
            formatter={(v: number) => [`${Math.round(v * 10) / 10} ${unit}`, label]}
          />
          <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
