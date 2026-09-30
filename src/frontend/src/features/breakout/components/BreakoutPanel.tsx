import { keepPreviousData, useMutation, useQuery } from '@tanstack/react-query'
import { useRoomInfo } from '@livekit/components-react'
import { useTranslation } from 'react-i18next'
import { css } from '@/styled-system/css'
import { Button, Div, Text } from '@/primitives'
import { queryClient } from '@/api/queryClient'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import {
  breakoutSessionKey,
  closeBreakoutSession,
  fetchBreakoutSession,
  type BreakoutSession,
} from '../api'
import { readBreakoutSessionId } from '../utils/transitions'
import { BreakoutSetup } from './BreakoutSetup'

const ActiveSession = ({
  roomId,
  session,
}: {
  roomId: string
  session: BreakoutSession
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout' })
  const close = useMutation({
    mutationFn: () => closeBreakoutSession(roomId, session.id),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: breakoutSessionKey(roomId) }),
  })

  return (
    <>
      <ul
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: '0.75rem',
        })}
      >
        {session.rooms.map((room) => (
          <li key={room.id}>
            <Text variant="bodyXsBold">{room.name}</Text>
            <Text variant="xsNote" wrap="pretty">
              {room.participants.map((p) => p.name).join(', ') ||
                t('active.empty')}
            </Text>
          </li>
        ))}
      </ul>
      {close.isError && (
        <Text variant="warning" role="alert">
          {t('error')}
        </Text>
      )}
      <Button
        variant="primary"
        fullWidth
        isDisabled={close.isPending}
        onPress={() => close.mutate()}
      >
        {t('active.close')}
      </Button>
    </>
  )
}

export const BreakoutPanel = () => {
  const roomId = useRoomData()?.id
  const { metadata } = useRoomInfo()
  // Keyed on the announced session, so an open or close elsewhere refetches.
  const announced = readBreakoutSessionId(metadata)
  const { data, isPending, isError } = useQuery({
    queryKey: [...breakoutSessionKey(roomId), announced],
    queryFn: () => fetchBreakoutSession(roomId as string),
    enabled: !!roomId,
    retry: false,
    placeholderData: keepPreviousData,
  })
  // The list answers 404 with the flag off; the metadata still allows a close.
  const session: BreakoutSession | null =
    data ??
    (isError && announced
      ? { id: announced, status: 'active', rooms: [] }
      : null)

  // A failed list with nothing announced: Open would fail as well, so no form.
  if (!roomId || isPending || (isError && !session)) return null

  return (
    <Div
      display="flex"
      overflowY="auto"
      padding="0 1.5rem 1.5rem"
      flexGrow={1}
      flexDirection="column"
      gap="1rem"
    >
      {session ? (
        <ActiveSession roomId={roomId} session={session} />
      ) : (
        <BreakoutSetup roomId={roomId} />
      )}
    </Div>
  )
}
