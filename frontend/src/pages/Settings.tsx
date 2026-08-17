import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../api/client'
import { Settings as SettingsIcon, Link, Brain, Bike, RefreshCw, Check, ExternalLink, Download, Database, Zap, Cpu } from 'lucide-react'

export default function Settings() {
  const queryClient = useQueryClient()
  const { data: settings } = useQuery({ queryKey: ['settings'], queryFn: () => api.settings() })
  const { data: stravaStatus } = useQuery({ queryKey: ['strava-status'], queryFn: () => api.stravaStatus() })
  const { data: intervalsStatus } = useQuery({ queryKey: ['intervals-status'], queryFn: () => api.intervalsStatus() })
  const { data: syncStatus } = useQuery({ queryKey: ['sync-status'], queryFn: () => api.syncStatus() })

  const [ftp, setFtp] = useState(200)
  const [thresholdPace, setThresholdPace] = useState(300)
  const [swimCssPace, setSwimCssPace] = useState(105)
  const [intervalsKey, setIntervalsKey] = useState('')
  const [intervalsId, setIntervalsId] = useState('')
  const [aiProvider, setAiProvider] = useState('claude')
  const [ollamaUrl, setOllamaUrl] = useState('http://localhost:11434')
  const [ollamaModelLight, setOllamaModelLight] = useState('llama3.1')
  const [ollamaModelHeavy, setOllamaModelHeavy] = useState('llama3.1:70b')
  const [claudeModelLight, setClaudeModelLight] = useState('claude-haiku-4-5-20251001')
  const [claudeModelHeavy, setClaudeModelHeavy] = useState('claude-sonnet-4-20250514')
  const [openaiModelLight, setOpenaiModelLight] = useState('gpt-4o-mini')
  const [openaiModelHeavy, setOpenaiModelHeavy] = useState('gpt-4o')
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (settings) {
      setFtp(settings.ftp || 200)
      setThresholdPace(settings.threshold_pace || 300)
      setSwimCssPace(settings.swim_css_pace || 105)
      setAiProvider(settings.ai_provider || 'claude')
      setOllamaUrl(settings.ollama_url || 'http://localhost:11434')
      setOllamaModelLight(settings.ollama_model_light || 'llama3.1')
      setOllamaModelHeavy(settings.ollama_model_heavy || 'llama3.1:70b')
      setClaudeModelLight(settings.claude_model_light || 'claude-haiku-4-5-20251001')
      setClaudeModelHeavy(settings.claude_model_heavy || 'claude-sonnet-4-20250514')
      setOpenaiModelLight(settings.openai_model_light || 'gpt-4o-mini')
      setOpenaiModelHeavy(settings.openai_model_heavy || 'gpt-4o')
    }
  }, [settings])

  const updateSettings = useMutation({
    mutationFn: (data: any) => api.updateSettings(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  const saveIntervals = useMutation({
    mutationFn: () => api.saveIntervals(intervalsKey, intervalsId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['intervals-status'] }),
  })

  const triggerSync = useMutation({
    mutationFn: () => api.triggerSync(),
    onSuccess: () => {
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['sync-status'] }), 2000)
    },
  })

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold flex items-center gap-2">
        <SettingsIcon className="w-5 h-5" /> Settings
      </h1>

      {/* Two columns at lg+ so sections use the available width instead of
         leaving the right half of a desktop viewport empty; each section
         stays narrow enough internally that form fields don't stretch
         awkwardly wide. Grid auto-flow pairs them row-major (1+2, 3+4...). */}
      <div className="space-y-6 lg:space-y-0 lg:grid lg:grid-cols-2 lg:gap-6 lg:items-start">
      {/* Connections */}
      <Section title="Connections" icon={<Link className="w-4 h-4" />}>
        <div className="space-y-4">
          <div className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary">
            <div>
              <div className="text-sm font-medium">Strava</div>
              <div className="text-xs text-slate-500">
                {stravaStatus?.connected
                  ? `Connected (Athlete ${stravaStatus.athlete_id})`
                  : 'Not connected'}
              </div>
            </div>
            {stravaStatus?.connected ? (
              <span className="text-xs text-success flex items-center gap-1">
                <Check className="w-3.5 h-3.5" /> Connected
              </span>
            ) : (
              <a
                href="/api/auth/strava"
                className="px-3 py-1.5 text-xs rounded-lg bg-[#FC4C02] text-white hover:bg-[#e04400] transition-colors flex items-center gap-1"
              >
                <ExternalLink className="w-3 h-3" /> Connect
              </a>
            )}
          </div>

          <div className="p-3 rounded-lg bg-bg-tertiary space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">intervals.icu</div>
                <div className="text-xs text-slate-500">
                  {intervalsStatus?.connected
                    ? `Connected (${intervalsStatus.athlete_id})`
                    : 'Not connected'}
                </div>
              </div>
              {intervalsStatus?.connected && (
                <span className="text-xs text-success flex items-center gap-1">
                  <Check className="w-3.5 h-3.5" /> Connected
                </span>
              )}
            </div>
            {!intervalsStatus?.connected && (
              <div className="space-y-2">
                <input
                  type="text"
                  placeholder="API Key"
                  value={intervalsKey}
                  onChange={(e) => setIntervalsKey(e.target.value)}
                  className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
                />
                <input
                  type="text"
                  placeholder="Athlete ID (e.g. i12345)"
                  value={intervalsId}
                  onChange={(e) => setIntervalsId(e.target.value)}
                  className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5 placeholder:text-slate-600"
                />
                <button
                  onClick={() => saveIntervals.mutate()}
                  disabled={!intervalsKey || !intervalsId}
                  className="px-3 py-1.5 text-xs rounded-lg bg-accent text-bg-primary hover:bg-accent-hover transition-colors disabled:opacity-50"
                >
                  Save
                </button>
              </div>
            )}
          </div>
        </div>
      </Section>

      {/* Sync */}
      <Section title="Data Sync" icon={<RefreshCw className="w-4 h-4" />}>
        <div className="flex items-center justify-between p-3 rounded-lg bg-bg-tertiary">
          <div>
            <div className="text-sm">{syncStatus?.activities_count || 0} activities synced</div>
            <div className="text-xs text-slate-500">
              {syncStatus?.last_sync ? `Last sync: ${new Date(syncStatus.last_sync).toLocaleString()}` : 'Never synced'}
            </div>
          </div>
          <button
            onClick={() => triggerSync.mutate()}
            disabled={syncStatus?.sync_in_progress}
            className="px-3 py-1.5 text-xs rounded-lg bg-accent text-bg-primary hover:bg-accent-hover transition-colors disabled:opacity-50 flex items-center gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncStatus?.sync_in_progress ? 'animate-spin' : ''}`} />
            {syncStatus?.sync_in_progress ? 'Syncing...' : 'Sync Now'}
          </button>
        </div>
      </Section>

      {/* Training */}
      <Section title="Training" icon={<Bike className="w-4 h-4" />}>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-slate-400 block mb-1">FTP (Functional Threshold Power)</label>
            <div className="flex gap-2">
              <input
                type="number"
                value={ftp}
                onChange={(e) => setFtp(Number(e.target.value))}
                className="w-32 bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
              />
              <span className="text-sm text-slate-500 self-center">watts</span>
            </div>
            <p className="text-[11px] text-slate-600 mt-1">Cycling workouts are prescribed against this.</p>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Run threshold pace</label>
            <div className="flex gap-2">
              <PaceInput seconds={thresholdPace} onChange={setThresholdPace} />
              <span className="text-sm text-slate-500 self-center">min/km</span>
            </div>
            <p className="text-[11px] text-slate-600 mt-1">
              Roughly your 1-hour race pace. Run workouts are prescribed against this.
            </p>
          </div>

          <div>
            <label className="text-xs text-slate-400 block mb-1">Swim threshold (CSS) pace</label>
            <div className="flex gap-2">
              <PaceInput seconds={swimCssPace} onChange={setSwimCssPace} />
              <span className="text-sm text-slate-500 self-center">min/100m</span>
            </div>
            <p className="text-[11px] text-slate-600 mt-1">
              Your critical swim speed. Swim sets are prescribed against this.
            </p>
          </div>
        </div>
      </Section>

      {/* AI */}
      <Section title="AI Coach" icon={<Brain className="w-4 h-4" />}>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Provider</label>
            <select
              value={aiProvider}
              onChange={(e) => setAiProvider(e.target.value)}
              className="bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
            >
              <option value="claude">Claude API</option>
              <option value="openai">OpenAI API</option>
              <option value="ollama">Ollama (Free, Local)</option>
            </select>
          </div>

          <div className="p-3 rounded-lg bg-bg-tertiary space-y-3">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Zap className="w-3 h-3 text-accent" />
              <span>Model Tiers — light for quick tasks, heavy for plan generation</span>
            </div>

            {aiProvider === 'ollama' && (
              <>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">Ollama URL</label>
                  <input
                    type="text"
                    value={ollamaUrl}
                    onChange={(e) => setOllamaUrl(e.target.value)}
                    className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                  />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">
                      <Zap className="w-3 h-3 inline mr-1" />Light Model
                    </label>
                    <input
                      type="text"
                      value={ollamaModelLight}
                      onChange={(e) => setOllamaModelLight(e.target.value)}
                      className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-slate-400 block mb-1">
                      <Cpu className="w-3 h-3 inline mr-1" />Heavy Model
                    </label>
                    <input
                      type="text"
                      value={ollamaModelHeavy}
                      onChange={(e) => setOllamaModelHeavy(e.target.value)}
                      className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                    />
                  </div>
                </div>
              </>
            )}

            {aiProvider === 'claude' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">
                    <Zap className="w-3 h-3 inline mr-1" />Light Model
                  </label>
                  <input
                    type="text"
                    value={claudeModelLight}
                    onChange={(e) => setClaudeModelLight(e.target.value)}
                    className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">
                    <Cpu className="w-3 h-3 inline mr-1" />Heavy Model
                  </label>
                  <input
                    type="text"
                    value={claudeModelHeavy}
                    onChange={(e) => setClaudeModelHeavy(e.target.value)}
                    className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                  />
                </div>
              </div>
            )}

            {aiProvider === 'openai' && (
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs text-slate-400 block mb-1">
                    <Zap className="w-3 h-3 inline mr-1" />Light Model
                  </label>
                  <input
                    type="text"
                    value={openaiModelLight}
                    onChange={(e) => setOpenaiModelLight(e.target.value)}
                    className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                  />
                </div>
                <div>
                  <label className="text-xs text-slate-400 block mb-1">
                    <Cpu className="w-3 h-3 inline mr-1" />Heavy Model
                  </label>
                  <input
                    type="text"
                    value={openaiModelHeavy}
                    onChange={(e) => setOpenaiModelHeavy(e.target.value)}
                    className="w-full bg-bg-primary text-sm rounded-lg px-3 py-2 border border-white/5"
                  />
                </div>
              </div>
            )}

            <p className="text-[10px] text-slate-600">
              Light: single sessions, plan adjustments &middot; Heavy: weekly plans, multi-week programs
            </p>
          </div>
        </div>
      </Section>

      {/* Data Export */}
      <Section title="Data Export" icon={<Download className="w-4 h-4" />}>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => api.exportActivities('csv')}
            className="px-3 py-1.5 text-xs rounded-lg bg-bg-tertiary hover:bg-bg-hover transition-colors"
          >
            Export Activities (CSV)
          </button>
          <button
            onClick={() => api.exportActivities('json')}
            className="px-3 py-1.5 text-xs rounded-lg bg-bg-tertiary hover:bg-bg-hover transition-colors"
          >
            Export Activities (JSON)
          </button>
        </div>
      </Section>

      {/* Token Usage */}
      <Section title="AI Usage" icon={<Database className="w-4 h-4" />}>
        <TokenUsageDisplay />
      </Section>
      </div>

      <button
        onClick={() => updateSettings.mutate({
          ftp, threshold_pace: thresholdPace, swim_css_pace: swimCssPace,
          ai_provider: aiProvider, ollama_url: ollamaUrl,
          ollama_model_light: ollamaModelLight, ollama_model_heavy: ollamaModelHeavy,
          claude_model_light: claudeModelLight, claude_model_heavy: claudeModelHeavy,
          openai_model_light: openaiModelLight, openai_model_heavy: openaiModelHeavy,
        })}
        className="px-4 py-2 text-sm rounded-lg bg-accent text-bg-primary hover:bg-accent-hover transition-colors flex items-center gap-2"
      >
        {saved ? <><Check className="w-4 h-4" /> Saved!</> : 'Save Settings'}
      </button>
    </div>
  )
}

function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-4">
      <h2 className="text-sm font-medium text-slate-300 flex items-center gap-2 mb-3">
        {icon} {title}
      </h2>
      {children}
    </div>
  )
}

function TokenUsageDisplay() {
  const { data } = useQuery({ queryKey: ['token-usage'], queryFn: () => api.settings() })
  const { data: usage } = useQuery({
    queryKey: ['ai-usage'],
    queryFn: async () => {
      try {
        const res = await fetch('/api/ai/usage')
        if (!res.ok) return null
        return res.json()
      } catch { return null }
    },
  })

  if (!usage) {
    return <p className="text-xs text-slate-500">No AI usage recorded yet.</p>
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-3 gap-3">
        <div className="p-2 rounded-lg bg-bg-tertiary text-center">
          <div className="text-lg font-bold">{usage.total_calls || 0}</div>
          <div className="text-[10px] text-slate-500">Total Calls</div>
        </div>
        <div className="p-2 rounded-lg bg-bg-tertiary text-center">
          <div className="text-lg font-bold">{((usage.total_tokens || 0) / 1000).toFixed(1)}k</div>
          <div className="text-[10px] text-slate-500">Tokens Used</div>
        </div>
        <div className="p-2 rounded-lg bg-bg-tertiary text-center">
          <div className="text-lg font-bold">${(usage.estimated_cost || 0).toFixed(3)}</div>
          <div className="text-[10px] text-slate-500">Est. Cost</div>
        </div>
      </div>
      {usage.provider === 'ollama' && (
        <p className="text-[10px] text-success">Running locally via Ollama — no API cost</p>
      )}
      {usage.recent_calls?.length > 0 && (
        <div className="space-y-1 mt-2">
          <span className="text-[10px] text-slate-600 uppercase tracking-wider">Recent</span>
          {usage.recent_calls.slice(-5).reverse().map((c: any, i: number) => (
            <div key={i} className="flex items-center justify-between text-[10px] text-slate-500">
              <div className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full ${c.tier === 'heavy' ? 'bg-accent' : 'bg-success'}`} />
                <span className="text-slate-400">{c.model || c.provider}</span>
                <span className="text-slate-600">{c.tier}</span>
              </div>
              <span>${c.cost?.toFixed(4)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}


// Paces are natural to think about as mm:ss but are stored as seconds.
function PaceInput({ seconds, onChange }: { seconds: number; onChange: (s: number) => void }) {
  const mins = Math.floor(seconds / 60)
  const secs = seconds % 60
  const set = (m: number, s: number) =>
    onChange(Math.max(20, Math.min(59 * 60 + 59, m * 60 + s)))

  return (
    <div className="flex items-center gap-1">
      <input
        type="number"
        min={0}
        max={59}
        value={mins}
        onChange={(e) => set(Number(e.target.value), secs)}
        className="w-16 bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5 text-right"
      />
      <span className="text-slate-500">:</span>
      <input
        type="number"
        min={0}
        max={59}
        value={String(secs).padStart(2, '0')}
        onChange={(e) => set(mins, Math.min(59, Math.max(0, Number(e.target.value))))}
        className="w-16 bg-bg-tertiary text-sm rounded-lg px-3 py-2 border border-white/5"
      />
    </div>
  )
}
