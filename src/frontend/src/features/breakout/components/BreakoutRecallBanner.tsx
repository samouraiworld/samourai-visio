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
import type { BreakoutTiming } from '../hooks/useBreakoutTimer'
import { BREAKOUT_DEFAULTS } from '../utils/constants'
import { srOnly } from '@/styles/a11y'

interface BreakoutRecallBannerProps {
  onRecall: () => void
  timing?: BreakoutTiming | null
}

export const BreakoutRecallBanner = ({
  onRecall,
  timing,
}: BreakoutRecallBannerProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.participant' })
  const { remaining, hasTimer, isExpired } = useBreakoutTimer(timing)
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
        bottom: 'room-control-bar',
        insetInline: 0,
        marginInline: 'auto',
        width: 'fit',
        maxWidth: 'full',
        paddingBlock: 0.75,
        paddingInline: 1.5,
        borderRadius: '8',
        backgroundColor: 'danger',
        color: 'danger.text',
        fontSize: 14,
        fontWeight: '600',
        zIndex: 50,
      })}
    >
      <span aria-hidden="true">{t('returningIn', { seconds: remaining })}</span>
      <span className={srOnly} role="status" aria-live="polite">
        {t('returningIn', {
          seconds: BREAKOUT_DEFAULTS.RECALL_WARNING_SECONDS,
        })}
      </span>
    </div>
  )
}
