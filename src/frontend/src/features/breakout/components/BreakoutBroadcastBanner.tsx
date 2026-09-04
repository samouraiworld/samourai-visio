/**
 * Floating announcement banner shown to participants when the host
 * broadcasts a message to all breakout rooms.
 */

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

  return (
    <div
      className={css({
        position: 'absolute',
        top: 4,
        insetInline: 0,
        marginInline: 'auto',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 0.75,
        paddingBlock: 0.625,
        paddingInline: 1.25,
        borderRadius: '8',
        backgroundColor: 'primary',
        color: 'primary.text',
        boxShadow: 'box',
        zIndex: 100,
        width: 'full',
        maxWidth: 'room-side-panel',
        borderWidth: 1,
        borderStyle: 'solid',
        borderColor: 'primary.warm',
      })}
      role="alert"
      aria-live="polite"
    >
      <RiMegaphoneLine size={20} className={css({ flexShrink: 0 })} />
      <div className={css({ display: 'flex', flexDirection: 'column' })}>
        <span
          className={css({
            fontSize: 12,
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
            fontSize: 14,
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
          marginLeft: 0.5,
          padding: 0.25,
          borderRadius: 'full',
          backgroundColor: 'transparent',
          border: 'none',
          color: 'primary.text',
          cursor: 'pointer',
          opacity: 0.8,
          _hover: { opacity: 1, backgroundColor: 'primary.hover' },
        })}
      >
        <RiCloseLine size={18} />
      </button>
    </div>
  )
}
