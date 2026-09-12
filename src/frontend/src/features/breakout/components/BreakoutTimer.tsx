/**
 * Synchronized breakout room countdown timer.
 *
 * Displays remaining time formatted as mm:ss, with warning state
 * when under 60 seconds. Supports both side-panel and video-overlay variants.
 */

import { css } from '@/styled-system/css'
import { RiTimerLine } from '@remixicon/react'
import { useBreakoutTimer } from '../hooks/useBreakoutTimer'
import type { BreakoutTiming } from '../hooks/useBreakoutTimer'
import { BREAKOUT_DEFAULTS } from '../utils/constants'
import { findCrossedTimerMilestone } from '../utils/timerMilestones'
import { useTranslation } from 'react-i18next'
import { useEffect, useRef, useState } from 'react'
import { srOnly } from '@/styles/a11y'

const formatTime = (seconds: number): string => {
  const mins = Math.floor(Math.max(0, seconds) / 60)
  const secs = Math.floor(Math.max(0, seconds) % 60)
  return `${mins}:${secs.toString().padStart(2, '0')}`
}

interface BreakoutTimerProps {
  variant?: 'panel' | 'overlay'
  timing?: BreakoutTiming | null
}

export const BreakoutTimer = ({
  variant = 'panel',
  timing,
}: BreakoutTimerProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.timer' })
  const { remaining, elapsed, hasTimer, isCountdown, isExpired } =
    useBreakoutTimer(timing)
  const previousRemaining = useRef<number | null>(null)
  const [announcement, setAnnouncement] = useState('')

  useEffect(() => {
    previousRemaining.current = null
    setAnnouncement('')
  }, [timing?.started_at])

  useEffect(() => {
    if (!isCountdown) return
    const previous = previousRemaining.current
    previousRemaining.current = remaining
    if (previous === null) return
    const crossedMilestone = findCrossedTimerMilestone(previous, remaining)
    if (crossedMilestone !== undefined) {
      setAnnouncement(t('remaining', { time: formatTime(crossedMilestone) }))
    }
  }, [isCountdown, remaining, t])

  if (!hasTimer) return null

  const isWarning =
    isCountdown &&
    remaining <= BREAKOUT_DEFAULTS.RECALL_WARNING_SECONDS &&
    remaining > 0

  const isOverlay = variant === 'overlay'

  return (
    <div
      className={css({
        display: 'flex',
        alignItems: 'center',
        gap: 0.375,
        paddingBlock: 0.25,
        paddingInline: 0.75,
        borderRadius: 'full',
        fontSize: 12,
        fontWeight: '600',
        fontVariantNumeric: 'tabular-nums',
        transition: 'all 0.3s ease',
        backgroundColor: isWarning
          ? 'danger.subtle'
          : isOverlay
            ? 'control.subtle'
            : 'primary.subtle',
        color: isWarning
          ? 'danger.subtle-text'
          : isOverlay
            ? 'primary.text'
            : 'primary.subtle-text',
      })}
      role="timer"
      aria-live="off"
      aria-label={
        isCountdown
          ? t('remaining', { time: formatTime(remaining) })
          : t('elapsed', { time: formatTime(elapsed) })
      }
    >
      <RiTimerLine size={15} aria-hidden="true" />
      <span>
        {isCountdown
          ? isExpired
            ? '0:00'
            : formatTime(remaining)
          : t('open', { time: formatTime(elapsed) })}
      </span>
      <span className={srOnly} aria-live="polite" aria-atomic="true">
        {announcement}
      </span>
    </div>
  )
}
