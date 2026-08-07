// Chart colors live here because Recharts needs literal values, not Tailwind
// classes. Keep these in sync with tailwind.config.js — this is the same muted
// palette, just in a form SVG can consume.

export const COLORS = {
  bgSecondary: '#141414',
  bgTertiary: '#1c1c1c',
  border: '#3a3a3a',
  grid: '#282828',
  text: '#bdbdbd',
  textMuted: '#6e6e6e',

  accent: '#e8e8e8',
  success: '#8faa7d',
  warning: '#c2a15c',
  danger: '#c07a72',
  info: '#7d95ab',
  neutral: '#8a97a3',
  lavender: '#9b8fa8',
  teal: '#74a3a8',
} as const

export const SPORT_COLORS: Record<string, string> = {
  running: '#8faa7d',
  cycling: '#7d95ab',
  swimming: '#74a3a8',
  strength: '#c08f56',
  walking: '#9b8fa8',
  rowing: '#74a3a8',
  other: '#8a97a3',
}

// Metric colors, chosen so several can share a chart without shouting.
export const METRIC_COLORS = {
  heartRate: '#c07a72',
  power: '#c2a15c',
  cadence: '#9b8fa8',
  speed: '#7d95ab',
  elevation: '#8a97a3',
  ctl: '#8faa7d',
  atl: '#7d95ab',
  tsb: '#c07a72',
  hrv: '#9b8fa8',
  sleep: '#7d95ab',
  weight: '#8a97a3',
} as const

// Shared Recharts tooltip styling.
export const TOOLTIP_STYLE = {
  background: COLORS.bgTertiary,
  border: `1px solid ${COLORS.border}`,
  borderRadius: 10,
  fontSize: 12,
  color: COLORS.text,
  boxShadow: '0 8px 24px rgba(0, 0, 0, 0.45)',
} as const
