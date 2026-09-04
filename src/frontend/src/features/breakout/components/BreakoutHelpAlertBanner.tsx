/**
 * Floating SOS help alert banner shown to the host when a breakout participant
 * clicks 'Ask for Help'.
 */

import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation } from 'react-i18next'
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

  return (
    <div
      className={css({
        position: 'absolute',
        bottom: 'room-control-bar',
        insetInline: 0,
        marginInline: 'auto',
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 0.75,
        paddingBlock: 0.75,
        paddingInline: 1.25,
        borderRadius: '8',
        backgroundColor: 'danger',
        color: 'danger.text',
        boxShadow: 'box',
        zIndex: 110,
        width: 'full',
        maxWidth: 'room-side-panel',
        borderWidth: 1,
        borderStyle: 'solid',
        borderColor: 'danger.subtle',
      })}
      role="alert"
      aria-live="assertive"
    >
      <RiAlarmWarningLine size={22} className={css({ flexShrink: 0 })} />
      <div className={css({ display: 'flex', flexDirection: 'column' })}>
        <span
          className={css({
            fontSize: 12,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            fontWeight: '700',
            opacity: 0.9,
          })}
        >
          {t('title')}
        </span>
        <span className={css({ fontSize: 14, fontWeight: '500' })}>
          {t('body', { participantName, roomName })}
        </span>
      </div>

      <div
        className={css({
          display: 'flex',
          alignItems: 'center',
          gap: 0.5,
          marginLeft: 0.5,
        })}
      >
        <Button
          variant="primary"
          size="sm"
          onPress={onJoinRoom}
          className={css({
            backgroundColor: 'danger.text',
            color: 'danger',
            fontWeight: '700',
            _hover: { backgroundColor: 'danger.subtle' },
          })}
        >
          <RiLoginBoxLine size={15} />
          <span className={css({ marginLeft: 0.25 })}>{t('joinRoom')}</span>
        </Button>

        <button
          onClick={onDismiss}
          aria-label={t('dismiss')}
          className={css({
            padding: 0.25,
            borderRadius: 'full',
            backgroundColor: 'transparent',
            border: 'none',
            color: 'danger.text',
            cursor: 'pointer',
            opacity: 0.8,
            _hover: { opacity: 1, backgroundColor: 'danger.hover' },
          })}
        >
          <RiCloseLine size={18} />
        </button>
      </div>
    </div>
  )
}
