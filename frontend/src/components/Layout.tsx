import { useState } from 'react'
import { Outlet, NavLink } from 'react-router-dom'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard, Activity, CalendarDays, Heart,
  Brain, Bike, Settings as SettingsIcon, Zap,
  ClipboardList, Plus, ListChecks, Lock,
} from 'lucide-react'
import { api } from '../api/client'
import LogActivityModal from './LogActivityModal'

const nav = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/week', icon: ClipboardList, label: 'Week' },
  { to: '/plan', icon: ListChecks, label: 'Plan' },
  { to: '/activities', icon: Activity, label: 'Activities' },
  { to: '/calendar', icon: CalendarDays, label: 'Calendar' },
  { to: '/wellness', icon: Heart, label: 'Wellness' },
  { to: '/coach', icon: Brain, label: 'AI Coach' },
  { to: '/trainer', icon: Bike, label: 'Trainer' },
  { to: '/settings', icon: SettingsIcon, label: 'Settings' },
]

/** Sign out. Renders only when the server is actually asking for a PIN —
 *  an instance with no PIN set has nothing to lock. */
function LockButton() {
  const { data: session } = useQuery({ queryKey: ['session'], queryFn: () => api.session() })

  const logout = useMutation({
    mutationFn: () => api.logout(),
    // Reload for the same reason as login, and it guarantees no fetched
    // training data is left sitting in memory behind the lock screen.
    onSuccess: () => window.location.reload(),
  })

  if (!session?.required) return null

  return (
    <button
      onClick={() => logout.mutate()}
      className="mx-3 mb-3 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-slate-500 hover:text-slate-300 hover:bg-bg-hover transition-colors"
    >
      <Lock className="w-[18px] h-[18px]" />
      Lock
    </button>
  )
}

export default function Layout() {
  const [logOpen, setLogOpen] = useState(false)

  return (
    <div className="flex h-screen bg-bg-primary">
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-56 bg-bg-secondary border-r border-white/5">
        <div className="flex items-center gap-2 px-5 py-5">
          <Zap className="w-6 h-6 text-accent" />
          <span className="text-lg font-bold tracking-tight">Pulse</span>
        </div>

        <button
          onClick={() => setLogOpen(true)}
          className="mx-3 mb-3 flex items-center justify-center gap-2 px-3 py-2 rounded-lg text-sm bg-accent/10 text-accent hover:bg-accent/20 transition-colors"
        >
          <Plus className="w-4 h-4" /> Log Activity
        </button>

        <nav className="flex-1 px-3 space-y-0.5">
          {nav.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-accent/15 text-accent'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-bg-hover'
                }`
              }
            >
              <Icon className="w-[18px] h-[18px]" />
              {label}
            </NavLink>
          ))}
        </nav>

        <LockButton />
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto pb-20 md:pb-0">
        <div className="max-w-6xl mx-auto p-4 md:p-6">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 bg-bg-secondary border-t border-white/5 flex justify-around py-2 z-50">
        {[nav[0], nav[1], nav[2], nav[3]].map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] transition-colors ${
                isActive ? 'text-accent' : 'text-slate-500'
              }`
            }
          >
            <Icon className="w-5 h-5" />
            {label}
          </NavLink>
        ))}
        <button
          onClick={() => setLogOpen(true)}
          className="flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] text-accent"
        >
          <Plus className="w-5 h-5" />
          Log
        </button>
        <NavLink
          to="/trainer"
          className={({ isActive }) =>
            `flex flex-col items-center gap-0.5 px-2 py-1 text-[10px] transition-colors ${
              isActive ? 'text-accent' : 'text-slate-500'
            }`
          }
        >
          <Bike className="w-5 h-5" />
          Trainer
        </NavLink>
      </nav>

      <LogActivityModal open={logOpen} onClose={() => setLogOpen(false)} />
    </div>
  )
}
