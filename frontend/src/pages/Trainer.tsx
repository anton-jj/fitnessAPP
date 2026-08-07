import { useState, useEffect, useRef, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import {
  Bluetooth, BluetoothOff, Play, Pause, Square, Zap, Heart,
  Gauge, RotateCcw, ChevronUp, ChevronDown,
} from 'lucide-react'

// FTMS UUIDs
const FTMS_SERVICE = 0x1826
const INDOOR_BIKE_DATA = 0x2AD2
const CONTROL_POINT = 0x2AD9
const HEART_RATE_SERVICE = 0x180D
const HR_MEASUREMENT = 0x2A37

interface TrainerData {
  power: number
  cadence: number
  speed: number
  heartRate: number
}

interface WorkoutStep {
  type: string
  duration: number
  power?: number
  power_start?: number
  power_end?: number
  cadence?: number
  repeat?: number
  rest?: WorkoutStep
}

function expandSteps(steps: WorkoutStep[]): WorkoutStep[] {
  const expanded: WorkoutStep[] = []
  for (const step of steps) {
    if (step.repeat && step.repeat > 1 && step.rest) {
      for (let i = 0; i < step.repeat; i++) {
        expanded.push({ ...step, repeat: undefined, rest: undefined })
        if (i < step.repeat - 1) expanded.push(step.rest)
      }
    } else {
      expanded.push(step)
    }
  }
  return expanded
}

function getTargetPower(step: WorkoutStep, elapsed: number, ftp: number): number {
  if (step.power_start != null && step.power_end != null) {
    const pct = Math.min(elapsed / step.duration, 1)
    return Math.round((step.power_start + (step.power_end - step.power_start) * pct) * ftp)
  }
  return Math.round((step.power || 0.5) * ftp)
}

export default function Trainer() {
  const [searchParams] = useSearchParams()
  const workoutId = searchParams.get('workout')

  const { data: workoutData } = useQuery({
    queryKey: ['workout', workoutId],
    queryFn: () => api.workout(Number(workoutId)),
    enabled: !!workoutId,
  })
  const { data: settingsData } = useQuery({
    queryKey: ['settings'],
    queryFn: () => api.settings(),
  })

  const ftp = settingsData?.ftp || 200

  const [connected, setConnected] = useState(false)
  const [hrConnected, setHrConnected] = useState(false)
  const [trainerData, setTrainerData] = useState<TrainerData>({ power: 0, cadence: 0, speed: 0, heartRate: 0 })
  const [isRunning, setIsRunning] = useState(false)
  const [elapsed, setElapsed] = useState(0)
  const [currentStepIdx, setCurrentStepIdx] = useState(0)
  const [stepElapsed, setStepElapsed] = useState(0)
  const [manualTarget, setManualTarget] = useState(ftp)
  const [mode, setMode] = useState<'workout' | 'free'>('free')
  const [powerHistory, setPowerHistory] = useState<number[]>([])
  const [hrHistory, setHrHistory] = useState<number[]>([])

  const controlPointRef = useRef<any>(null)
  const intervalRef = useRef<number | null>(null)

  const steps = workoutData?.steps ? expandSteps(workoutData.steps) : []
  const currentStep = steps[currentStepIdx]

  useEffect(() => {
    if (workoutData?.steps?.length) setMode('workout')
  }, [workoutData])

  const bluetoothSupported = typeof navigator !== 'undefined' && !!navigator.bluetooth

  const connectTrainer = async () => {
    if (!bluetoothSupported) return
    try {
      const device = await navigator.bluetooth.requestDevice({
        filters: [{ services: [FTMS_SERVICE] }],
        optionalServices: [HEART_RATE_SERVICE],
      })
      const server = await device.gatt!.connect()

      const ftmsService = await server.getPrimaryService(FTMS_SERVICE)
      const bikeData = await ftmsService.getCharacteristic(INDOOR_BIKE_DATA)
      controlPointRef.current = await ftmsService.getCharacteristic(CONTROL_POINT)

      await bikeData.startNotifications()
      bikeData.addEventListener('characteristicvaluechanged', (e: any) => {
        const dv = e.target.value as DataView
        const flags = dv.getUint16(0, true)
        let offset = 2

        let speed = 0, cadence = 0, power = 0
        if (!(flags & 0x01)) { speed = dv.getUint16(offset, true) * 0.01; offset += 2 }
        if (flags & 0x02) { cadence = dv.getUint16(offset, true) * 0.5; offset += 2 }
        if (flags & 0x04) { offset += 2 } // avg speed
        if (flags & 0x08) { offset += 2 } // avg cadence
        if (flags & 0x10) { offset += 4 } // total distance
        if (flags & 0x20) { offset += 4 } // resistance
        if (flags & 0x40) { power = dv.getInt16(offset, true); offset += 2 }

        setTrainerData((prev) => ({ ...prev, power, cadence, speed }))
      })

      try {
        const hrService = await server.getPrimaryService(HEART_RATE_SERVICE)
        const hrChar = await hrService.getCharacteristic(HR_MEASUREMENT)
        await hrChar.startNotifications()
        hrChar.addEventListener('characteristicvaluechanged', (e: any) => {
          const dv = e.target.value as DataView
          const flags = dv.getUint8(0)
          const hr = flags & 0x01 ? dv.getUint16(1, true) : dv.getUint8(1)
          setTrainerData((prev) => ({ ...prev, heartRate: hr }))
        })
        setHrConnected(true)
      } catch { /* HR not available on trainer, user can connect separate */ }

      setConnected(true)
    } catch (err) {
      console.error('Connection failed:', err)
    }
  }

  const connectHR = async () => {
    if (!bluetoothSupported) return
    try {
      const device = await navigator.bluetooth.requestDevice({
        filters: [{ services: [HEART_RATE_SERVICE] }],
      })
      const server = await device.gatt!.connect()
      const service = await server.getPrimaryService(HEART_RATE_SERVICE)
      const char = await service.getCharacteristic(HR_MEASUREMENT)
      await char.startNotifications()
      char.addEventListener('characteristicvaluechanged', (e: any) => {
        const dv = e.target.value as DataView
        const flags = dv.getUint8(0)
        const hr = flags & 0x01 ? dv.getUint16(1, true) : dv.getUint8(1)
        setTrainerData((prev) => ({ ...prev, heartRate: hr }))
      })
      setHrConnected(true)
    } catch (err) {
      console.error('HR connection failed:', err)
    }
  }

  const setTargetPower = useCallback(async (watts: number) => {
    if (!controlPointRef.current) return
    const buf = new ArrayBuffer(3)
    const dv = new DataView(buf)
    dv.setUint8(0, 0x05) // Set Target Power opcode
    dv.setInt16(1, watts, true)
    try {
      await controlPointRef.current.writeValue(buf)
    } catch (err) {
      console.error('Failed to set power:', err)
    }
  }, [])

  useEffect(() => {
    if (!isRunning) {
      if (intervalRef.current) clearInterval(intervalRef.current)
      return
    }

    intervalRef.current = window.setInterval(() => {
      setElapsed((e) => e + 1)
      setStepElapsed((se) => se + 1)
      setTrainerData((td: TrainerData) => {
        setPowerHistory((h: number[]) => [...h.slice(-3600), td.power])
        setHrHistory((h: number[]) => [...h.slice(-3600), td.heartRate])
        return td
      })
    }, 1000)

    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [isRunning])

  useEffect(() => {
    if (!isRunning || !connected) return

    if (mode === 'workout' && currentStep) {
      const target = getTargetPower(currentStep, stepElapsed, ftp)
      setTargetPower(target)

      if (stepElapsed >= currentStep.duration) {
        if (currentStepIdx < steps.length - 1) {
          setCurrentStepIdx((i) => i + 1)
          setStepElapsed(0)
        } else {
          setIsRunning(false)
        }
      }
    } else if (mode === 'free') {
      setTargetPower(manualTarget)
    }
  }, [isRunning, connected, mode, stepElapsed, currentStep, currentStepIdx, ftp, manualTarget, setTargetPower, steps.length])

  const targetWatts = mode === 'workout' && currentStep
    ? getTargetPower(currentStep, stepElapsed, ftp)
    : manualTarget

  const totalDuration = steps.reduce((sum, s) => sum + s.duration, 0)
  const avgPower = powerHistory.length > 0
    ? Math.round(powerHistory.reduce((a, b) => a + b, 0) / powerHistory.length)
    : 0

  const formatTime = (s: number) => {
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${sec.toString().padStart(2, '0')}`
    return `${m}:${sec.toString().padStart(2, '0')}`
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Smart Trainer</h1>
        <div className="flex gap-2">
          <button
            onClick={connectHR}
            disabled={!bluetoothSupported}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              hrConnected
                ? 'bg-danger/10 border-danger/30 text-danger'
                : 'bg-bg-secondary border-white/5 hover:bg-bg-hover text-slate-400'
            }`}
          >
            <Heart className="w-3.5 h-3.5" />
            {hrConnected ? 'HR Connected' : 'Connect HR'}
          </button>
          <button
            onClick={connectTrainer}
            disabled={!bluetoothSupported}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg border transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${
              connected
                ? 'bg-success/10 border-success/30 text-success'
                : 'bg-accent hover:bg-accent-hover text-bg-primary border-accent'
            }`}
          >
            {connected ? <Bluetooth className="w-3.5 h-3.5" /> : <BluetoothOff className="w-3.5 h-3.5" />}
            {connected ? 'Connected' : 'Connect Trainer'}
          </button>
        </div>
      </div>

      {!bluetoothSupported && (
        <div className="p-3 rounded-xl bg-warning/10 border border-warning/20 text-sm text-warning">
          Web Bluetooth is not available. Use Chrome or Edge over HTTPS to connect a smart trainer.
        </div>
      )}

      {/* Workout profile visualization */}
      {mode === 'workout' && steps.length > 0 && (
        <WorkoutProfile steps={steps} ftp={ftp} currentStepIdx={currentStepIdx} stepElapsed={stepElapsed} />
      )}

      {/* Main metrics */}
      <div className="grid grid-cols-3 gap-3">
        <MetricBox
          label="POWER"
          value={trainerData.power}
          unit="W"
          target={targetWatts}
          color={trainerData.power > targetWatts * 1.05 ? '#c07a72' : trainerData.power < targetWatts * 0.95 ? '#7d95ab' : '#8faa7d'}
          large
        />
        <MetricBox label="CADENCE" value={trainerData.cadence} unit="rpm" color="#9b8fa8" large />
        <MetricBox label="HEART RATE" value={trainerData.heartRate} unit="bpm" color="#c07a72" large />
      </div>

      <div className="grid grid-cols-4 gap-3">
        <MetricBox label="TARGET" value={targetWatts} unit="W" color="#c2a15c" />
        <MetricBox label="AVG POWER" value={avgPower} unit="W" color="#c08f56" />
        <MetricBox label="SPEED" value={Math.round(trainerData.speed * 10) / 10} unit="km/h" color="#7d95ab" />
        <MetricBox
          label="ELAPSED"
          value={formatTime(elapsed)}
          unit={mode === 'workout' ? `/ ${formatTime(totalDuration)}` : ''}
          color="#8a97a3"
        />
      </div>

      {/* Controls */}
      <div className="flex items-center justify-center gap-4">
        {mode === 'free' && (
          <div className="flex items-center gap-2 mr-4">
            <button
              onClick={() => setManualTarget((t: number) => Math.max(50, t - 10))}
              className="p-2 rounded-lg bg-bg-secondary hover:bg-bg-hover"
            >
              <ChevronDown className="w-5 h-5" />
            </button>
            <div className="text-center min-w-[80px]">
              <div className="text-2xl font-bold font-mono">{manualTarget}</div>
              <div className="text-[10px] text-slate-500 uppercase">Target W</div>
            </div>
            <button
              onClick={() => setManualTarget((t: number) => t + 10)}
              className="p-2 rounded-lg bg-bg-secondary hover:bg-bg-hover"
            >
              <ChevronUp className="w-5 h-5" />
            </button>
          </div>
        )}
        <button
          onClick={() => setIsRunning(!isRunning)}
          disabled={!connected}
          className={`p-4 rounded-full transition-colors disabled:opacity-30 ${
            isRunning ? 'bg-warning/20 text-warning hover:bg-warning/30' : 'bg-success/20 text-success hover:bg-success/30'
          }`}
        >
          {isRunning ? <Pause className="w-6 h-6" /> : <Play className="w-6 h-6" />}
        </button>
        <button
          onClick={() => {
            setIsRunning(false)
            setElapsed(0)
            setStepElapsed(0)
            setCurrentStepIdx(0)
            setPowerHistory([])
            setHrHistory([])
          }}
          className="p-3 rounded-full bg-bg-secondary hover:bg-bg-hover text-slate-400"
        >
          <RotateCcw className="w-5 h-5" />
        </button>
      </div>

      {/* Mode toggle */}
      <div className="flex justify-center gap-2">
        <button
          onClick={() => setMode('free')}
          className={`px-4 py-1.5 text-xs rounded-full transition-colors ${
            mode === 'free' ? 'bg-accent text-bg-primary' : 'bg-bg-secondary text-slate-400 hover:bg-bg-hover'
          }`}
        >
          Free Ride
        </button>
        <button
          onClick={() => setMode('workout')}
          disabled={steps.length === 0}
          className={`px-4 py-1.5 text-xs rounded-full transition-colors disabled:opacity-30 ${
            mode === 'workout' ? 'bg-accent text-bg-primary' : 'bg-bg-secondary text-slate-400 hover:bg-bg-hover'
          }`}
        >
          Workout {workoutData?.name ? `(${workoutData.name})` : ''}
        </button>
      </div>

      {/* Current step info */}
      {mode === 'workout' && currentStep && isRunning && (
        <div className="bg-bg-secondary rounded-xl border border-white/5 p-4 text-center">
          <div className="text-xs text-slate-400 uppercase mb-1">{currentStep.type}</div>
          <div className="text-lg font-bold">
            {targetWatts}W
            {currentStep.cadence && <span className="text-sm text-slate-400 ml-2">{currentStep.cadence} rpm</span>}
          </div>
          <div className="text-sm text-slate-500 mt-1">
            {formatTime(Math.max(0, currentStep.duration - stepElapsed))} remaining
            <span className="mx-2">·</span>
            Step {currentStepIdx + 1} of {steps.length}
          </div>
        </div>
      )}
    </div>
  )
}

function MetricBox({ label, value, unit, color, target, large }: {
  label: string; value: string | number; unit: string; color: string; target?: number; large?: boolean
}) {
  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-3 text-center">
      <div className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</div>
      <div className={`font-mono font-bold ${large ? 'text-3xl md:text-4xl' : 'text-xl'}`} style={{ color }}>
        {value}
      </div>
      <div className="text-[10px] text-slate-500">{unit}</div>
    </div>
  )
}

function WorkoutProfile({ steps, ftp, currentStepIdx, stepElapsed }: {
  steps: WorkoutStep[]; ftp: number; currentStepIdx: number; stepElapsed: number
}) {
  const totalDuration = steps.reduce((s, st) => s + st.duration, 0)
  const maxPower = Math.max(...steps.map((s) => Math.max(s.power || 0, s.power_start || 0, s.power_end || 0))) * ftp

  const stepColors: Record<string, string> = {
    warmup: '#8faa7d',
    interval: '#c07a72',
    rest: '#7d95ab',
    cooldown: '#74a3a8',
    steady: '#c2a15c',
  }

  let elapsed = 0
  for (let i = 0; i < currentStepIdx; i++) elapsed += steps[i].duration
  elapsed += stepElapsed
  const progressPct = (elapsed / totalDuration) * 100

  return (
    <div className="bg-bg-secondary rounded-xl border border-white/5 p-3">
      <svg viewBox={`0 0 ${totalDuration} ${maxPower * 1.1}`} className="w-full h-24 md:h-32" preserveAspectRatio="none">
        {(() => {
          let x = 0
          return steps.map((step, i) => {
            const startX = x
            const w = step.duration
            const h1 = (step.power_start ?? step.power ?? 0.5) * ftp
            const h2 = (step.power_end ?? step.power ?? 0.5) * ftp
            const maxH = maxPower * 1.1
            const color = stepColors[step.type] || '#9b8fa8'
            const opacity = i < currentStepIdx ? 0.3 : i === currentStepIdx ? 0.8 : 0.5
            x += w

            return (
              <polygon
                key={i}
                points={`${startX},${maxH} ${startX},${maxH - h1} ${startX + w},${maxH - h2} ${startX + w},${maxH}`}
                fill={color}
                opacity={opacity}
              />
            )
          })
        })()}
        <line
          x1={(progressPct / 100) * totalDuration}
          y1={0}
          x2={(progressPct / 100) * totalDuration}
          y2={maxPower * 1.1}
          stroke="white"
          strokeWidth={totalDuration * 0.003}
          opacity={0.8}
        />
      </svg>
    </div>
  )
}
