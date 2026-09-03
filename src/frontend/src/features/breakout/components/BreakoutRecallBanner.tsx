/**
 * Warning banner: "Returning to main room in Xs"
 *
 * Shown when the timer is within the recall warning threshold.
 * Also auto-triggers the return when timer reaches 0.
 */

import { useEffect, useRef } from 'react'
import { css } from '@/styled-system/css'
import { useTranslation } from 'react-i18next'
import { useBreakoutTimer } from '../hooks/useBreakoutTimer'
import { BREAKOUT_DEFAULTS } from '../utils/constants'

interface BreakoutRecallBannerProps {
  onRecall: () => void
}

export const BreakoutRecallBanner = ({
  onRecall,
}: BreakoutRecallBannerProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.participant' })
  const { remaining, hasTimer, isExpired } = useBreakoutTimer()
  const hasRecalledRef = useRef(false)

  const isWarning =
    hasTimer &&
    remaining <= BREAKOUT_DEFAULTS.RECALL_WARNING_SECONDS &&
    remaining > 0

  // Auto-recall when timer expires
  useEffect(() => {
    if (isExpired && !hasRecalledRef.current) {
      hasRecalledRef.current = true
      onRecall()
    }
  }, [isExpired, onRecall])

  if (!isWarning) return null

  return (
    <div
      className={css({
        position: 'absolute',
        bottom: 'calc(var(--sizes-room-control-bar) + 0.5rem)',
        left: '50%',
        transform: 'translateX(-50%)',
        padding: '0.75rem 1.5rem',
        borderRadius: '0.75rem',
        backgroundColor: 'rgba(239, 68, 68, 0.9)',
        color: 'white',
        fontSize: '0.9375rem',
        fontWeight: '600',
        zIndex: 50,
        animation: 'pulse 2s ease-in-out infinite',
      })}
      role="alert"
      aria-live="assertive"
    >
      {t('returningIn', { seconds: remaining })}
    </div>
  )
}
