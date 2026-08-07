import {
  ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, Tooltip,
} from 'recharts'

const STREAM_CONFIG: Record<string, { color: string; label: string; unit: string }> = {
  hr: { color: '#c07a72', label: 'Heart Rate', unit: 'bpm' },
  power: { color: '#c2a15c', label: 'Power', unit: 'W' },
  cadence: { color: '#9b8fa8', label: 'Cadence', unit: 'rpm' },
  speed: { color: '#7d95ab', label: 'Speed', unit: 'km/h' },
  altitude: { color: '#8a97a3', label: 'Elevation', unit: 'm' },
}

interface Props {
  streams: Record<string, number[]>
  visibleStreams?: string[]
}

export default function StreamChart({ streams, visibleStreams }: Props) {
  if (!streams?.time?.length) {
    return (
      <div className="bg-bg-secondary rounded-xl border border-white/5 p-8 text-center text-slate-500">
        No stream data available for this activity.
      </div>
    )
  }

  const visible = visibleStreams || Object.keys(streams).filter((k) => k !== 'time' && k !== 'latlng')
  const data = streams.time.map((t, i) => {
    const point: any = { time: t }
    for (const key of visible) {
      if (streams[key]) {
        let val = streams[key][i]
        if (key === 'speed' && val) val = val * 3.6
        point[key] = val
      }
    }
    return point
  })

  const formatTime = (secs: number) => {
    const h = Math.floor(secs / 3600)
    const m = Math.floor((secs % 3600) / 60)
    return h > 0 ? `${h}:${m.toString().padStart(2, '0')}` : `${m}m`
  }

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
      <h2 className="text-sm font-medium text-slate-300 mb-4">Activity Streams</h2>
      <ResponsiveContainer width="100%" height={300}>
        <ComposedChart data={data} margin={{ top: 5, right: 5, bottom: 5, left: -10 }}>
          <XAxis
            dataKey="time"
            tickFormatter={formatTime}
            tick={{ fontSize: 11 }}
            interval="preserveStartEnd"
            minTickGap={60}
          />
          <YAxis yAxisId="left" tick={{ fontSize: 11 }} />
          {visible.includes('altitude') && (
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} />
          )}
          <Tooltip
            contentStyle={{
              background: '#1f1e1c',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelFormatter={(v) => formatTime(v as number)}
            formatter={(value: number, name: string) => {
              const cfg = STREAM_CONFIG[name]
              return [Math.round(value), cfg ? `${cfg.label} (${cfg.unit})` : name]
            }}
          />
          {visible.includes('altitude') && (
            <Area
              yAxisId="right"
              type="monotone"
              dataKey="altitude"
              stroke="#3e3934"
              fill="#2b2724"
              strokeWidth={1}
            />
          )}
          {visible.filter((s) => s !== 'altitude').map((stream) => (
            <Line
              key={stream}
              yAxisId="left"
              type="monotone"
              dataKey={stream}
              stroke={STREAM_CONFIG[stream]?.color || '#8a97a3'}
              strokeWidth={1.5}
              dot={false}
            />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}
