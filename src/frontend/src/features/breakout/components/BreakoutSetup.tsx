import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useParticipants } from '@livekit/components-react'
import { useTranslation } from 'react-i18next'
import { RiShuffleLine } from '@remixicon/react'
import { css } from '@/styled-system/css'
import { Button, Text } from '@/primitives'
import { Select } from '@/primitives/Select'
import { queryClient } from '@/api/queryClient'
import { breakoutSessionKey, createBreakoutSession } from '../api'
import {
  MAX_ROOMS,
  MIN_ROOMS,
  buildRooms,
  countUnassigned,
  isAssignable,
  shuffleAssignments,
  type Assignments,
} from '../utils/setup'

const UNASSIGNED = -1
const ROOM_COUNTS = Array.from(
  { length: MAX_ROOMS - MIN_ROOMS + 1 },
  (_, i) => MIN_ROOMS + i
)

export const BreakoutSetup = ({ roomId }: { roomId: string }) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout' })
  const [roomCount, setRoomCount] = useState(MIN_ROOMS)
  const [assignments, setAssignments] = useState<Assignments>({})

  const people = useParticipants()
    .filter(isAssignable)
    .map((p) => ({ identity: p.identity, name: p.name || p.identity }))
  const identities = people.map((p) => p.identity)
  const unassigned = countUnassigned(identities, assignments, roomCount)
  const roomNames = Array.from({ length: roomCount }, (_, i) =>
    t('roomName', { number: i + 1 })
  )
  const roomItems = [
    { value: UNASSIGNED, label: t('setup.unassignedOption') },
    ...roomNames.map((label, value) => ({ value, label })),
  ]

  const open = useMutation({
    mutationFn: () =>
      createBreakoutSession(roomId, {
        rooms: buildRooms(roomNames, people, assignments),
      }),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: breakoutSessionKey(roomId) }),
  })

  return (
    <>
      <Select
        aria-label={t('setup.roomCount')}
        label={t('setup.roomCount')}
        items={ROOM_COUNTS.map((n) => ({ value: n, label: String(n) }))}
        selectedKey={roomCount}
        onSelectionChange={(key) => setRoomCount(Number(key))}
      />
      <div
        className={css({
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        })}
      >
        <Text variant="bodyXsBold">
          {people.length === 0
            ? t('setup.nobody')
            : unassigned > 0
              ? t('setup.unassigned', { count: unassigned })
              : t('setup.allAssigned')}
        </Text>
        <Button
          variant="secondaryText"
          size="sm"
          isDisabled={people.length === 0}
          onPress={() =>
            setAssignments(shuffleAssignments(identities, roomCount))
          }
        >
          <RiShuffleLine size={16} aria-hidden />
          {t('setup.shuffle')}
        </Button>
      </div>
      <ul
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        })}
      >
        {people.map((p) => {
          const index = assignments[p.identity] ?? UNASSIGNED
          return (
            <li
              key={p.identity}
              className={css({
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '0.5rem',
              })}
            >
              <Text variant="sm" wrap="pretty">
                {p.name}
              </Text>
              <div className={css({ width: '10rem', flexShrink: 0 })}>
                <Select
                  aria-label={t('setup.assign', { name: p.name })}
                  label=""
                  items={roomItems}
                  selectedKey={index < roomCount ? index : UNASSIGNED}
                  onSelectionChange={(key) =>
                    setAssignments((previous) => ({
                      ...previous,
                      [p.identity]: Number(key),
                    }))
                  }
                />
              </div>
            </li>
          )
        })}
      </ul>
      {open.isError && (
        <Text variant="warning" role="alert">
          {t('error')}
        </Text>
      )}
      <Button
        variant="primary"
        fullWidth
        isDisabled={open.isPending || unassigned === people.length}
        onPress={() => open.mutate()}
      >
        {t('setup.open')}
      </Button>
    </>
  )
}
