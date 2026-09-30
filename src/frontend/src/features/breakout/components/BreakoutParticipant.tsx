import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { css } from '@/styled-system/css'
import { Spinner } from '@/primitives/Spinner'
import { breakoutStore } from '../store'
import { useBreakout, type Connect } from '../hooks/useBreakout'

export const BreakoutParticipant = ({
  mainRoomId,
  connect,
}: {
  mainRoomId: string
  connect: Connect
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.participant' })
  const { room, target, moveFailed } = useSnapshot(breakoutStore)
  useBreakout(mainRoomId, connect)

  if (target) {
    return (
      <div
        role="status"
        className={css({
          position: 'fixed',
          inset: 0,
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 1,
          backgroundColor: 'primaryDark.50',
          color: 'white',
          fontSize: 20,
        })}
      >
        <Spinner />
        {target === 'main'
          ? t('returning')
          : t('moving', { room: target.name })}
      </div>
    )
  }

  if (!room && !moveFailed) return null
  return (
    <div
      role="status"
      className={css({
        position: 'fixed',
        top: '10px',
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 10,
        paddingY: '0.25rem',
        paddingX: '0.75rem',
        borderRadius: '4px',
        backgroundColor: 'primaryDark.100',
        color: 'white',
      })}
    >
      {room ? t('currentRoom', { room: room.name }) : t('moveFailed')}
    </div>
  )
}
