import { Bike, Footprints, Waves, Dumbbell, Zap, type LucideIcon } from 'lucide-react'

/** Lucide icon per sport, used anywhere a workout/activity needs a compact
 *  visual marker (plan day cards, calendar chips). `Zap` is the fallback for
 *  sports without a dedicated icon (hiking, xcski, rowing, yoga, other...). */
export const SPORT_ICONS: Record<string, LucideIcon> = {
  cycling: Bike,
  running: Footprints,
  swimming: Waves,
  strength: Dumbbell,
}

export const SPORT_ICON_FALLBACK: LucideIcon = Zap

/** Solid background-color classes for small sport dots (calendar cells). */
export const SPORT_DOT_CLASS: Record<string, string> = {
  running: 'bg-sport-running',
  cycling: 'bg-sport-cycling',
  swimming: 'bg-sport-swimming',
  strength: 'bg-sport-strength',
}
export const SPORT_DOT_FALLBACK = 'bg-sport-other'

/** Tinted `/20` badge classes for sport icon chips (ActivityCard-style). */
export const SPORT_BADGE_CLASS: Record<string, string> = {
  running: 'bg-sport-running/20 text-sport-running',
  cycling: 'bg-sport-cycling/20 text-sport-cycling',
  swimming: 'bg-sport-swimming/20 text-sport-swimming',
  strength: 'bg-sport-strength/20 text-sport-strength',
}
export const SPORT_BADGE_FALLBACK = 'bg-sport-other/20 text-sport-other'

/** Outlined, low-fill classes for a *planned-but-not-done* calendar chip —
 *  same sport hue as SPORT_BADGE_CLASS but a dashed border instead of a
 *  solid fill, so a month reads "done" vs "upcoming" at a glance the way
 *  TrainingPeaks' filled-vs-outlined blocks do. */
export const SPORT_PLANNED_CLASS: Record<string, string> = {
  running: 'border-sport-running/40 bg-sport-running/[0.07] text-sport-running',
  cycling: 'border-sport-cycling/40 bg-sport-cycling/[0.07] text-sport-cycling',
  swimming: 'border-sport-swimming/40 bg-sport-swimming/[0.07] text-sport-swimming',
  strength: 'border-sport-strength/40 bg-sport-strength/[0.07] text-sport-strength',
}
export const SPORT_PLANNED_FALLBACK = 'border-sport-other/40 bg-sport-other/[0.07] text-sport-other'
