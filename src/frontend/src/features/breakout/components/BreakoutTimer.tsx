/**
 * Synchronized breakout room countdown timer.
 *
 * Displays remaining time formatted as mm:ss, with warning state
 * when under 60 seconds. Supports both side-panel and video-overlay variants.
 */

import { css } from '@/styled-system/css'
import { RiTimerLine } from '@remixicon/react'
import { useBreakoutTimer } from '../hooks/useBreakoutTimer'
import { BREAKOUT_DEFAULTS } from '../utils/constants'

const formatTime = (seconds: number): string => {
  const mins = Math.floor(Math.max(0, seconds) / 60)
  const secs = Math.floor(Math.max(0, seconds) % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

interface BreakoutTimerProps {
  variant?: 'panel' | 'overlay'
}

export const BreakoutTimer = ({ variant = 'panel' }: BreakoutTimerProps) => {
  const { remaining, elapsed, hasTimer, isCountdown, isExpired } =
    useBreakoutTimer()

  if (!hasTimer) return null

  const isWarning =
    isCountdown &&
    remaining <= BREAKOUT_DEFAULTS.RECALL_WARNING_SECONDS &&
    remaining > 0

  const isOverlay = variant === 'overlay'
  const bgColor = isWarning
    ? isOverlay
      ? 'rgba(239, 68, 68, 0.25)'
      : 'rgba(225, 0, 15, 0.12)'
    : isOverlay
      ? 'rgba(255, 255, 255, 0.12)'
      : 'rgba(0, 0, 145, 0.08)'

  const textColor = isWarning
    ? isOverlay
      ? '#ff8080'
      : '#ce0500'
    : isOverlay
      ? '#ffffff'
      : '#000091'

  return (
    <div
      className={css({
        display: 'flex',
        alignItems: 'center',
        gap: '0.375rem',
        padding: '0.25rem 0.75rem',
        borderRadius: '999px',
        fontSize: '0.8125rem',
        fontWeight: '600',
        fontVariantNumeric: 'tabular-nums',
        transition: 'all 0.3s ease',
      })}
      style={{
        backgroundColor: bgColor,
        color: textColor,
      }}
      role="timer"
      aria-live="polite"
      aria-label={
        isCountdown
          ? `Time remaining: ${formatTime(remaining)}`
          : `Elapsed time: ${formatTime(elapsed)}`
      }
    >
      <RiTimerLine size={15} aria-hidden="true" />
      <span>
        {isCountdown
          ? isExpired
            ? '0:00'
            : formatTime(remaining)
          : `${formatTime(elapsed)} (Open)`}
      </span>
    </div>
  )
}
