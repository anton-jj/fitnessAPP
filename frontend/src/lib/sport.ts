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
