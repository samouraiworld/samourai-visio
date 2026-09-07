import { useEffect, useState } from 'react'
import {
  computeTimerSnapshot,
  isSameTimerSnapshot,
  type BreakoutTiming,
} from '../utils/timerState'

export type { BreakoutTiming } from '../utils/timerState'

export const useBreakoutTimer = (timing?: BreakoutTiming | null) => {
  const [snapshot, setSnapshot] = useState(() =>
    computeTimerSnapshot(timing, Date.now())
  )

  useEffect(() => {
    const tick = () =>
      setSnapshot((previous) => {
        const next = computeTimerSnapshot(timing, Date.now())
        return isSameTimerSnapshot(previous, next) ? previous : next
      })
    tick()
    if (!computeTimerSnapshot(timing, Date.now()).hasTimer) return
    const interval = setInterval(tick, 1000)
    return () => clearInterval(interval)
  }, [timing])

  return snapshot
}
