/**
 * Overlay shown to participants when they are in a breakout room.
 *
 * Displays: current room name, timer, 'Ask for Help' button, and 'Return to Main Room' button.
 * Uses the shared semantic color tokens for consistent contrast and theming.
 */

import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'
import { useRequestBreakoutHelp } from '../api/useRequestBreakoutHelp'
import { useCancelBreakoutHelp } from '../api/useCancelBreakoutHelp'
import { useCurrentBreakoutAssignment } from '../api/useCurrentBreakoutAssignment'
import { BreakoutTimer } from './BreakoutTimer'
import { BreakoutRecallBanner } from './BreakoutRecallBanner'
import {
  RiArrowGoBackLine,
  RiQuestionLine,
  RiCheckLine,
} from '@remixicon/react'

interface BreakoutParticipantOverlayProps {
  onReturnToMain: () => void
  onReturnToAssigned: () => void
}

export const BreakoutParticipantOverlay = ({
  onReturnToMain,
  onReturnToAssigned,
}: BreakoutParticipantOverlayProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.participant' })
  const snap = useSnapshot(breakoutStore)
  const sessionId = snap.activeSessionId ?? undefined
  const roomId = snap.mainRoomId || snap.mainRoomSlug || undefined
  const { data: assignmentState } = useCurrentBreakoutAssignment(
    roomId,
    sessionId
  )
  const {
    mutateAsync: sendHelpRequest,
    isPending: isSendingHelp,
    isError: didHelpFail,
  } = useRequestBreakoutHelp()
  const {
    mutateAsync: cancelHelpRequest,
    isPending: isCancellingHelp,
    isError: didCancelFail,
  } = useCancelBreakoutHelp()

  // Find the display name of the current breakout room with fallback to transitionTargetName
  const roomName =
    assignmentState?.assignment?.breakout_room_name ??
    snap.transitionTargetName ??
    t('unknownRoom')
  const helpOpen = !!assignmentState?.help_request
  const isInBreakout = !!snap.currentBreakoutRoomLkName

  const handleAskForHelp = async () => {
    if (!sessionId || !roomId) return

    await sendHelpRequest({ roomId, sessionId })
  }

  const handleCancelHelp = async () => {
    if (!sessionId || !roomId) return
    await cancelHelpRequest({ roomId, sessionId })
  }

  return (
    <>
      <BreakoutRecallBanner
        onRecall={onReturnToMain}
        timing={assignmentState}
      />
      <div
        className={css({
          position: 'absolute',
          top: 0.75,
          insetInline: 0,
          marginInline: 'auto',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: 0.625,
          paddingBlock: 0.5,
          paddingInline: 1,
          borderRadius: '8',
          backgroundColor: 'greyscale.950',
          zIndex: 50,
          pointerEvents: 'auto',
          width: 'full',
          maxWidth: 'room-side-panel',
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: 'control.subtle',
        })}
      >
        <span
          className={css({
            color: 'primary.text',
            fontSize: 14,
            fontWeight: '600',
          })}
        >
          {t('currentRoom', { room: roomName })}
        </span>

        <BreakoutTimer variant="overlay" timing={assignmentState} />

        {/* Ask for Help Button */}
        <Button
          variant="secondaryText"
          size="sm"
          isDisabled={isSendingHelp || isCancellingHelp}
          onPress={helpOpen ? handleCancelHelp : handleAskForHelp}
          aria-label={helpOpen ? t('cancelHelp') : t('askForHelp')}
          tooltip={helpOpen ? t('cancelHelp') : t('askForHelpTooltip')}
          className={css({
            color: 'primary.text !important',
            _hover: { backgroundColor: 'primary.hover !important' },
          })}
        >
          {helpOpen ? <RiCheckLine size={15} /> : <RiQuestionLine size={15} />}
          <span
            className={css({
              fontSize: 12,
              marginLeft: 0.25,
              color: 'primary.text !important',
            })}
          >
            {helpOpen ? t('cancelHelp') : t('askForHelp')}
          </span>
        </Button>

        {/* Return to Main Room Button */}
        <Button
          variant="secondaryText"
          size="sm"
          onPress={isInBreakout ? onReturnToMain : onReturnToAssigned}
          aria-label={isInBreakout ? t('returnButton') : t('returnAssigned')}
          tooltip={isInBreakout ? t('returnButton') : t('returnAssigned')}
          className={css({
            color: 'primary.text !important',
            _hover: { backgroundColor: 'primary.hover !important' },
          })}
        >
          <RiArrowGoBackLine size={15} />
          <span
            className={css({
              fontSize: 12,
              marginLeft: 0.25,
              color: 'primary.text !important',
            })}
          >
            {isInBreakout ? t('returnButton') : t('returnAssigned')}
          </span>
        </Button>
      </div>
      {(didHelpFail || didCancelFail || snap.transitionError) && (
        <div
          role="alert"
          className={css({
            position: 'absolute',
            top: 4,
            insetInline: 0,
            marginInline: 'auto',
            width: 'fit',
            maxWidth: 'full',
            padding: 0.5,
            borderRadius: '8',
            backgroundColor: 'danger',
            color: 'danger.text',
          })}
        >
          {t('actionError')}
        </div>
      )}
    </>
  )
}
