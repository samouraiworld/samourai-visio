/**
 * Overlay shown to participants when they are in a breakout room.
 *
 * Displays: current room name, timer, 'Ask for Help' button, and 'Return to Main Room' button.
 * Minimal design — floating non-obstructive bar with WCAG AA compliant high contrast.
 */

import { useState } from 'react'
import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'
import { useRequestBreakoutHelp } from '../api/useRequestBreakoutHelp'
import { BreakoutTimer } from './BreakoutTimer'
import { BreakoutRecallBanner } from './BreakoutRecallBanner'
import {
  RiArrowGoBackLine,
  RiQuestionLine,
  RiCheckLine,
} from '@remixicon/react'

interface BreakoutParticipantOverlayProps {
  onReturnToMain: () => void
}

export const BreakoutParticipantOverlay = ({
  onReturnToMain,
}: BreakoutParticipantOverlayProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.participant' })
  const snap = useSnapshot(breakoutStore)
  const [helpSent, setHelpSent] = useState(false)

  const { mutateAsync: sendHelpRequest, isPending: isSendingHelp } =
    useRequestBreakoutHelp()

  // Find the display name of the current breakout room with fallback to transitionTargetName
  const roomName =
    snap.session?.breakout_rooms.find(
      (r) => r.livekit_room_name === snap.currentBreakoutRoomLkName
    )?.name ??
    snap.transitionTargetName ??
    'Breakout Room'

  const handleAskForHelp = async () => {
    const sessionId = snap.activeSessionId
    const roomId = snap.mainRoomId || snap.mainRoomSlug
    const breakoutRoomId = snap.assignedRoomId
    if (!sessionId || !roomId || !breakoutRoomId) return

    try {
      await sendHelpRequest({
        roomId,
        sessionId,
        breakoutRoomId,
      })
      setHelpSent(true)
      setTimeout(() => setHelpSent(false), 30000)
    } catch (err) {
      console.error('Failed to request breakout help:', err)
    }
  }

  return (
    <>
      <BreakoutRecallBanner onRecall={onReturnToMain} />
      <div
        className={css({
          position: 'absolute',
          top: '0.75rem',
          left: '50%',
          transform: 'translateX(-50%)',
          display: 'flex',
          alignItems: 'center',
          gap: '0.625rem',
          padding: '0.5rem 1rem',
          borderRadius: '999px',
          backgroundColor: 'rgba(0, 0, 0, 0.75)',
          backdropFilter: 'blur(8px)',
          zIndex: 50,
          pointerEvents: 'auto',
          border: '1px solid rgba(255, 255, 255, 0.2)',
        })}
      >
        <span
          className={css({
            color: 'white',
            fontSize: '0.875rem',
            fontWeight: '600',
          })}
        >
          {t('currentRoom', { room: roomName })}
        </span>

        <BreakoutTimer variant="overlay" />

        {/* Ask for Help Button — WCAG AA crisp white high contrast */}
        <Button
          variant="secondaryText"
          size="sm"
          isDisabled={isSendingHelp || helpSent}
          onPress={handleAskForHelp}
          aria-label={t('askForHelp') ?? 'Ask for Help'}
          tooltip={
            t('askForHelpTooltip') ?? 'Notify the host you need assistance'
          }
          className={css({
            color: 'white !important',
            _hover: { backgroundColor: 'rgba(255, 255, 255, 0.15) !important' },
          })}
        >
          {helpSent ? (
            <RiCheckLine size={15} color="white" />
          ) : (
            <RiQuestionLine size={15} color="white" />
          )}
          <span
            className={css({
              fontSize: '0.8125rem',
              marginLeft: '0.25rem',
              color: 'white !important',
            })}
          >
            {helpSent
              ? (t('helpRequested') ?? 'Help requested')
              : (t('askForHelp') ?? 'Ask for Help')}
          </span>
        </Button>

        {/* Return to Main Room Button — WCAG AA crisp white high contrast */}
        <Button
          variant="secondaryText"
          size="sm"
          onPress={onReturnToMain}
          aria-label={t('returnButton')}
          tooltip={t('returnButton')}
          className={css({
            color: 'white !important',
            _hover: { backgroundColor: 'rgba(255, 255, 255, 0.15) !important' },
          })}
        >
          <RiArrowGoBackLine size={15} color="white" />
          <span
            className={css({
              fontSize: '0.8125rem',
              marginLeft: '0.25rem',
              color: 'white !important',
            })}
          >
            {t('returnButton')}
          </span>
        </Button>
      </div>
    </>
  )
}
