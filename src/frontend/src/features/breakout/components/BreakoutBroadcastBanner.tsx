/**
 * Floating announcement banner shown to participants when the host
 * broadcasts a message to all breakout rooms.
 */

import { useEffect } from 'react'
import { css } from '@/styled-system/css'
import { useTranslation } from 'react-i18next'
import { RiMegaphoneLine, RiCloseLine } from '@remixicon/react'

interface BreakoutBroadcastBannerProps {
  message: string
  onDismiss: () => void
}

export const BreakoutBroadcastBanner = ({
  message,
  onDismiss,
}: BreakoutBroadcastBannerProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.broadcast' })

  // Auto-dismiss after 10 seconds
  useEffect(() => {
    const timer = setTimeout(onDismiss, 10000)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div
      className={css({
        position: 'absolute',
        top: '4.5rem',
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        padding: '0.625rem 1.25rem',
        borderRadius: '0.5rem',
        backgroundColor: 'rgba(0, 0, 145, 0.92)',
        color: 'white',
        boxShadow: '0 8px 24px rgba(0, 0, 0, 0.4)',
        backdropFilter: 'blur(8px)',
        zIndex: 100,
        maxWidth: '90vw',
        border: '1px solid rgba(255, 255, 255, 0.2)',
      })}
      role="alert"
      aria-live="polite"
    >
      <RiMegaphoneLine size={20} className={css({ flexShrink: 0 })} />
      <div className={css({ display: 'flex', flexDirection: 'column' })}>
        <span
          className={css({
            fontSize: '0.75rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontWeight: '700',
            opacity: 0.85,
          })}
        >
          {t('title')}
        </span>
        <span
          className={css({
            fontSize: '0.9375rem',
            fontWeight: '500',
            wordBreak: 'break-word',
          })}
        >
          {message}
        </span>
      </div>
      <button
        onClick={onDismiss}
        aria-label={t('dismiss')}
        className={css({
          marginLeft: '0.5rem',
          padding: '0.25rem',
          borderRadius: '999px',
          backgroundColor: 'transparent',
          border: 'none',
          color: 'white',
          cursor: 'pointer',
          opacity: 0.8,
          _hover: { opacity: 1, backgroundColor: 'rgba(255, 255, 255, 0.15)' },
        })}
      >
        <RiCloseLine size={18} />
      </button>
    </div>
  )
}
