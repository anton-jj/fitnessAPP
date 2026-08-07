import {
  ResponsiveContainer, ComposedChart, Area, Line, XAxis, YAxis,
  Tooltip, Legend, ReferenceLine,
} from 'recharts'
import { format, parseISO } from 'date-fns'

interface Props {
  data: Array<{ date: string; ctl?: number; atl?: number; tsb?: number; daily_tss?: number }>
}

export default function FitnessChart({ data }: Props) {
  if (!data.length) {
    return (
      <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
        No fitness data yet. Connect your accounts and sync to see your PMC chart.
      </div>
    )
  }

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
      <h2 className="text-sm font-medium text-slate-300 mb-4">Performance Management</h2>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -10 }}>
          <defs>
            <linearGradient id="tsbGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#8faa7d" stopOpacity={0.15} />
              <stop offset="95%" stopColor="#8faa7d" stopOpacity={0} />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="date"
            tickFormatter={(d) => format(parseISO(d), 'MMM d')}
            tick={{ fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: '#1f1e1c',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(d) => format(parseISO(d as string), 'EEE, MMM d')}
            formatter={(value: number, name: string) => [
              Math.round(value),
              name === 'ctl' ? 'Fitness (CTL)' : name === 'atl' ? 'Fatigue (ATL)' : 'Form (TSB)',
            ]}
          />
          <Legend
            formatter={(v) =>
              v === 'ctl' ? 'Fitness' : v === 'atl' ? 'Fatigue' : 'Form'
            }
          />
          <ReferenceLine y={0} stroke="#2b2724" strokeDasharray="3 3" />
          <Area
            type="monotone"
            dataKey="tsb"
            stroke="#8faa7d"
            fill="url(#tsbGrad)"
            strokeWidth={1.5}
          />
          <Line
            type="monotone"
            dataKey="ctl"
            stroke="#7d95ab"
            strokeWidth={2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="atl"
            stroke="#c07a72"
            strokeWidth={2}
            dot={false}
            strokeDasharray="4 2"
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
