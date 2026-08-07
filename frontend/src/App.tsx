import { Routes, Route, Navigate } from 'react-router-dom'
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

export default function App() {
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
