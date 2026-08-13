import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { Zap, Lock } from 'lucide-react'
import { api } from '../api/client'

export default function Login({ onSuccess }: { onSuccess: () => void }) {
  const [pin, setPin] = useState('')

  const login = useMutation({
    mutationFn: () => api.login(pin),
    onSuccess: () => {
      setPin('')
      onSuccess()
    },
  })

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-xs">
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-2 mb-2">
            <Zap className="w-7 h-7 text-accent" />
            <span className="text-2xl font-bold">Pulse</span>
          </div>
          <p className="text-sm text-slate-400">Enter your PIN to continue</p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (pin && !login.isPending) login.mutate()
          }}
          className="bg-bg-secondary rounded-xl border border-white/5 p-5 space-y-3"
        >
          <div className="relative">
            <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="password"
              inputMode="numeric"
              autoFocus
              autoComplete="current-password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="PIN"
              className="w-full bg-bg-tertiary border border-white/5 rounded-lg pl-9 pr-3 py-2.5 text-sm tracking-widest focus:outline-none focus:border-accent/40 transition-colors"
            />
          </div>

          <button
            type="submit"
            disabled={!pin || login.isPending}
            className="w-full bg-accent hover:bg-accent-hover text-bg-primary text-sm font-medium py-2.5 rounded-lg transition-colors disabled:opacity-40"
          >
            {login.isPending ? 'Checking…' : 'Unlock'}
          </button>

          {login.isError && (
            <p className="text-xs text-danger text-center">
              {(login.error as Error).message}
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
