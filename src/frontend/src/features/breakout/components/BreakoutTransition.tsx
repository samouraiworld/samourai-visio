/**
 * Loading overlay shown during room transitions.
 *
 * Displayed briefly while the LiveKitRoom component remounts
 * with a new token/room name.
 */

import { css } from '@/styled-system/css'
import { useTranslation } from 'react-i18next'
import { Spinner } from '@/primitives/Spinner'
import { useSnapshot } from 'valtio'
import { breakoutStore } from '../stores/breakout'
import { useIsInBreakoutRoom } from '../hooks/useIsInBreakoutRoom'

export const BreakoutTransition = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.transition' })
  const snap = useSnapshot(breakoutStore)
  const { currentBreakoutRoomLkName } = useIsInBreakoutRoom()

  const targetName = snap.transitionTargetName || t('unknownRoom')
  const message = currentBreakoutRoomLkName
    ? t('returningToMain')
    : t('movingTo', { room: targetName })

  return (
    <div
      className={css({
        position: 'fixed',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        backgroundColor: 'greyscale.950',
        zIndex: 9999,
        gap: 1,
      })}
      role="alert"
      aria-live="assertive"
    >
      <Spinner />
      <p
        className={css({
          color: 'primary.text',
          fontSize: 20,
          fontWeight: '500',
        })}
      >
        {message}
      </p>
    </div>
  )
}
