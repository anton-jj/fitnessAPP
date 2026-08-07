import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend,
} from 'recharts'
import { format, parseISO } from 'date-fns'

const SPORT_COLORS: Record<string, string> = {
  cycling: '#7d95ab',
  running: '#8faa7d',
  swimming: '#74a3a8',
  strength: '#c2a15c',
  hiking: '#9b8fa8',
  xcski: '#b58fa8',
  other: '#9b8fa8',
}

interface Props {
  data: any[]
  metric?: 'hours' | 'tss' | 'km'
}

export default function VolumeChart({ data, metric = 'hours' }: Props) {
  if (!data.length) {
    return (
      <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
        No volume data yet.
      </div>
    )
  }

  const sports = new Set<string>()
  for (const entry of data) {
    for (const key of Object.keys(entry)) {
      if (key.endsWith(`_${metric}`)) {
        sports.add(key.replace(`_${metric}`, ''))
      }
    }
  }

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
      <h2 className="text-sm font-medium text-slate-300 mb-4">
        Weekly Volume ({metric === 'hours' ? 'Hours' : metric === 'tss' ? 'TSS' : 'Distance'})
      </h2>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -10 }}>
          <XAxis
            dataKey="week"
            tickFormatter={(d) => {
              try { return format(parseISO(d), 'MMM d') } catch { return d }
            }}
            tick={{ fontSize: 11 }}
          />
          <YAxis tick={{ fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: '#1f1e1c',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(d) => {
              try { return `Week of ${format(parseISO(d as string), 'MMM d')}` } catch { return d }
            }}
          />
          <Legend />
          {Array.from(sports).map((sport) => (
            <Bar
              key={sport}
              dataKey={`${sport}_${metric}`}
              name={sport.charAt(0).toUpperCase() + sport.slice(1)}
              stackId="a"
              fill={SPORT_COLORS[sport] || SPORT_COLORS.other}
              radius={[2, 2, 0, 0]}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
