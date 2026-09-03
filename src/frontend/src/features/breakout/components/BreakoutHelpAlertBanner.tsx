/**
 * Floating SOS help alert banner shown to the host when a breakout participant
 * clicks 'Ask for Help'.
 */

import { useEffect } from 'react'
import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation, Trans } from 'react-i18next'
import {
  RiAlarmWarningLine,
  RiCloseLine,
  RiLoginBoxLine,
} from '@remixicon/react'

interface BreakoutHelpAlertBannerProps {
  roomName: string
  participantName: string
  onJoinRoom: () => void
  onDismiss: () => void
}

export const BreakoutHelpAlertBanner = ({
  roomName,
  participantName,
  onJoinRoom,
  onDismiss,
}: BreakoutHelpAlertBannerProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.helpAlert' })

  // Auto-dismiss after 20 seconds
  useEffect(() => {
    const timer = setTimeout(onDismiss, 20000)
    return () => clearTimeout(timer)
  }, [onDismiss])

  return (
    <div
      className={css({
        position: 'absolute',
        top: '8rem',
        left: '50%',
        transform: 'translateX(-50%)',
        display: 'flex',
        alignItems: 'center',
        gap: '0.875rem',
        padding: '0.75rem 1.25rem',
        borderRadius: '0.625rem',
        backgroundColor: 'rgba(217, 83, 79, 0.95)', // Urgent red/coral
        color: 'white',
        boxShadow: '0 8px 28px rgba(0, 0, 0, 0.45)',
        backdropFilter: 'blur(8px)',
        zIndex: 110,
        maxWidth: '92vw',
        border: '1px solid rgba(255, 255, 255, 0.25)',
      })}
      role="alert"
      aria-live="assertive"
    >
      <RiAlarmWarningLine size={22} className={css({ flexShrink: 0 })} />
      <div className={css({ display: 'flex', flexDirection: 'column' })}>
        <span
          className={css({
            fontSize: '0.75rem',
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontWeight: '700',
            opacity: 0.9,
          })}
        >
          {t('title')}
        </span>
        <span className={css({ fontSize: '0.875rem', fontWeight: '500' })}>
          <Trans
            i18nKey="breakout.helpAlert.body"
            t={t}
            values={{ participantName, roomName }}
            components={{
              strong: <strong />,
            }}
          >
            <strong>{participantName}</strong> in <strong>{roomName}</strong> is
            asking for help
          </Trans>
        </span>
      </div>

      <div
        className={css({
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          marginLeft: '0.5rem',
        })}
      >
        <Button
          variant="primary"
          size="sm"
          onPress={onJoinRoom}
          className={css({
            backgroundColor: 'white',
            color: '#c9302c',
            fontWeight: '700',
            _hover: { backgroundColor: 'rgba(255, 255, 255, 0.9)' },
          })}
        >
          <RiLoginBoxLine size={15} />
          <span style={{ marginLeft: '0.25rem' }}>{t('joinRoom')}</span>
        </Button>

        <button
          onClick={onDismiss}
          aria-label={t('dismiss')}
          className={css({
            padding: '0.25rem',
            borderRadius: '999px',
            backgroundColor: 'transparent',
            border: 'none',
            color: 'white',
            cursor: 'pointer',
            opacity: 0.8,
            _hover: { opacity: 1, backgroundColor: 'rgba(255, 255, 255, 0.2)' },
          })}
        >
          <RiCloseLine size={18} />
        </button>
      </div>
    </div>
  )
}
