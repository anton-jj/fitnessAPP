import { useEffect } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { api, UNAUTHORIZED_EVENT } from './api/client'
import Login from './pages/Login'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Activities from './pages/Activities'
import ActivityDetail from './pages/ActivityDetail'
import Calendar from './pages/Calendar'
import Wellness from './pages/Wellness'
import AICoach from './pages/AICoach'
import Trainer from './pages/Trainer'
import Settings from './pages/Settings'
import WeeklyOverview from './pages/WeeklyOverview'
import Plan from './pages/Plan'
import Onboarding from './pages/Onboarding'

/** Holds the app behind the PIN screen when the server asks for one.
 *
 *  When no PIN is configured the server reports `required: false` and this is
 *  invisible — the app renders exactly as it did before. */
function AuthGate({ children }: { children: React.ReactNode }) {
  const queryClient = useQueryClient()
  const { data: session, isLoading } = useQuery({
    queryKey: ['session'],
    queryFn: () => api.session(),
    retry: false,
    staleTime: 60_000,
  })

  // A session can lapse mid-visit — the cookie expires, or the server restarts
  // without a persistent signing key. Re-check rather than leaving the user on
  // a page whose every request is failing.
  useEffect(() => {
    const recheck = () => queryClient.invalidateQueries({ queryKey: ['session'] })
    window.addEventListener(UNAUTHORIZED_EVENT, recheck)
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, recheck)
  }, [queryClient])

  if (isLoading) return null
  if (session?.required && !session.authenticated) {
    return (
      // Reload rather than nudging the cache: every query fetched while locked
      // out holds a 401, and clearing the cache mid-flight does not reliably
      // re-notify this gate. The cookie is set, so the reload lands inside.
      <Login onSuccess={() => window.location.reload()} />
    )
  }
  return <>{children}</>
}

export default function App() {
  return (
    <AuthGate>
      <AppRoutes />
    </AuthGate>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/week" element={<WeeklyOverview />} />
        <Route path="/activities" element={<Activities />} />
        <Route path="/activities/:id" element={<ActivityDetail />} />
        <Route path="/calendar" element={<Calendar />} />
        <Route path="/wellness" element={<Wellness />} />
        <Route path="/coach" element={<AICoach />} />
        <Route path="/plan" element={<Plan />} />
        <Route path="/trainer" element={<Trainer />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="/onboarding" element={<Onboarding />} />
      {/* Without this an unknown URL renders a blank page with no navigation. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
