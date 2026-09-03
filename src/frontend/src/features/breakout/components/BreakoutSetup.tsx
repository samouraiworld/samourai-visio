/**
 * Setup view for breakout rooms.
 *
 * Allows the moderator to:
 * 1. Configure number of rooms and extended duration (up to 4 hours).
 * 2. Assign participants manually (per-participant room selection)
 *    or automatically with 1-click random distribution.
 * 3. Open all rooms.
 */

import { useState, useCallback, useMemo } from 'react'
import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useParticipants } from '@livekit/components-react'
import { BREAKOUT_DEFAULTS } from '../utils/constants'
import { useCreateBreakoutSession } from '../api/useCreateBreakoutSession'
import { useRandomizeAssignments } from '../api/useRandomizeAssignments'
import { useAssignParticipants } from '../api/useAssignParticipants'
import { useUpdateBreakoutSession } from '../api/useUpdateBreakoutSession'
import { breakoutStore } from '../stores/breakout'
import type { BreakoutSession } from '../api/types'
import {
  RiShuffleLine,
  RiPlayFill,
  RiUserLine,
  RiCloseLine,
} from '@remixicon/react'

interface BreakoutSetupProps {
  roomUuid: string
  session: BreakoutSession | null
  onSessionCreated: (session: BreakoutSession) => void
}

const DURATION_OPTION_KEYS = [
  { value: '0', labelKey: 'durationOptions.none' },
  { value: '120', labelKey: 'durationOptions.2min' },
  { value: '300', labelKey: 'durationOptions.5min' },
  { value: '600', labelKey: 'durationOptions.10min' },
  { value: '900', labelKey: 'durationOptions.15min' },
  { value: '1200', labelKey: 'durationOptions.20min' },
  { value: '1800', labelKey: 'durationOptions.30min' },
  { value: '2700', labelKey: 'durationOptions.45min' },
  { value: '3600', labelKey: 'durationOptions.1h' },
  { value: '5400', labelKey: 'durationOptions.1h30' },
  { value: '7200', labelKey: 'durationOptions.2h' },
  { value: '10800', labelKey: 'durationOptions.3h' },
  { value: '14400', labelKey: 'durationOptions.4h' },
]

export const BreakoutSetup = ({
  roomUuid,
  session,
  onSessionCreated,
}: BreakoutSetupProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.setup' })
  const participants = useParticipants()

  const [numRooms, setNumRooms] = useState<number>(
    BREAKOUT_DEFAULTS.DEFAULT_ROOMS
  )
  const [duration, setDuration] = useState(
    String(BREAKOUT_DEFAULTS.DEFAULT_DURATION)
  )

  const { mutateAsync: createSession, isPending: isCreating } =
    useCreateBreakoutSession()
  const { mutateAsync: randomize, isPending: isRandomizing } =
    useRandomizeAssignments()
  const { mutateAsync: assignManual, isPending: isAssigning } =
    useAssignParticipants()
  const { mutateAsync: updateSession, isPending: isActivating } =
    useUpdateBreakoutSession()

  // Eligible participants (exclude local host)
  const assignableParticipants = useMemo(
    () => participants.filter((p) => !p.isLocal),
    [participants]
  )

  const handleCreate = useCallback(async () => {
    const created = await createSession({
      roomId: roomUuid,
      numRooms,
      durationSeconds: duration === '0' ? null : parseInt(duration, 10),
    })
    onSessionCreated(created)
    breakoutStore.session = created
  }, [roomUuid, numRooms, duration, createSession, onSessionCreated])

  const handleRandomize = useCallback(async () => {
    if (!session) return

    const participantList = assignableParticipants.map((p) => ({
      identity: p.identity,
      name: p.name ?? p.identity,
    }))

    const result = await randomize({
      roomId: roomUuid,
      sessionId: session.id,
      participants: participantList,
    })
    breakoutStore.session = result
  }, [session, assignableParticipants, roomUuid, randomize])

  const handleManualAssign = useCallback(
    async (
      participantIdentity: string,
      participantName: string,
      targetRoomId: string | null
    ) => {
      if (!session) return

      // Build updated assignments dictionary
      const newAssignments: Record<
        string,
        { identity: string; name: string }[]
      > = {}

      for (const room of session.breakout_rooms) {
        newAssignments[room.id] = room.assignments
          .filter((a) => a.participant_identity !== participantIdentity)
          .map((a) => ({
            identity: a.participant_identity,
            name: a.participant_name || a.participant_identity,
          }))
      }

      if (targetRoomId && newAssignments[targetRoomId]) {
        newAssignments[targetRoomId].push({
          identity: participantIdentity,
          name: participantName,
        })
      }

      const result = await assignManual({
        roomId: roomUuid,
        sessionId: session.id,
        assignments: newAssignments,
      })
      breakoutStore.session = result
    },
    [session, roomUuid, assignManual]
  )

  const handleActivate = useCallback(async () => {
    if (!session) return

    const updated = await updateSession({
      roomId: roomUuid,
      sessionId: session.id,
      status: 'active',
    })
    breakoutStore.session = updated
  }, [session, roomUuid, updateSession])

  // Total assigned
  const assignedCount =
    session?.breakout_rooms.reduce((sum, r) => sum + r.assignments.length, 0) ??
    0
  const unassignedCount = Math.max(
    0,
    assignableParticipants.length - assignedCount
  )

  // Map of participant identity -> assigned room ID
  const participantRoomMap = useMemo(() => {
    const map = new Map<string, string>()
    if (session) {
      for (const r of session.breakout_rooms) {
        for (const a of r.assignments) {
          map.set(a.participant_identity, r.id)
        }
      }
    }
    return map
  }, [session])

  return (
    <div
      className={css({
        display: 'flex',
        flexDirection: 'column',
        gap: '1rem',
        padding: '1rem',
        overflow: 'auto',
        flex: 1,
      })}
    >
      {!session && (
        <>
          {/* Room count selector */}
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            })}
          >
            <label className={css({ fontSize: '0.875rem', fontWeight: '500' })}>
              {t('roomCount')}
            </label>
            <div
              className={css({
                display: 'flex',
                gap: '0.5rem',
                flexWrap: 'wrap',
              })}
            >
              {Array.from(
                {
                  length:
                    BREAKOUT_DEFAULTS.MAX_ROOMS -
                    BREAKOUT_DEFAULTS.MIN_ROOMS +
                    1,
                },
                (_, i) => i + BREAKOUT_DEFAULTS.MIN_ROOMS
              ).map((n) => (
                <Button
                  key={n}
                  variant={n === numRooms ? 'primary' : 'secondaryText'}
                  size="sm"
                  onPress={() => setNumRooms(n)}
                  aria-label={`${n} rooms`}
                  aria-pressed={n === numRooms}
                >
                  {n}
                </Button>
              ))}
            </div>
          </div>

          {/* Extended Duration selector */}
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: '0.5rem',
            })}
          >
            <label className={css({ fontSize: '0.875rem', fontWeight: '500' })}>
              {t('duration')}
            </label>
            <select
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              aria-label={t('duration')}
              className={css({
                padding: '0.5rem 0.75rem',
                borderRadius: '0.375rem',
                border: '1px solid',
                borderColor: 'box.border',
                backgroundColor: 'box.bg',
                color: 'box.text',
                fontSize: '0.875rem',
                cursor: 'pointer',
                outline: 'none',
                _focus: {
                  borderColor: 'primary',
                  boxShadow: '0 0 0 2px rgba(0, 0, 145, 0.2)',
                },
              })}
            >
              {DURATION_OPTION_KEYS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {t(opt.labelKey)}
                </option>
              ))}
            </select>
          </div>

          <Button
            variant="primary"
            isDisabled={isCreating}
            onPress={handleCreate}
          >
            {t('create') ?? 'Create Breakout Rooms'}
          </Button>
        </>
      )}

      {session && session.status === 'configuring' && (
        <>
          {/* Room Cards List */}
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: '0.625rem',
            })}
          >
            {session.breakout_rooms.map((room) => (
              <div
                key={room.id}
                className={css({
                  padding: '0.75rem',
                  borderRadius: '0.5rem',
                  border: '1px solid',
                  borderColor: 'box.border',
                  backgroundColor: 'rgba(255, 255, 255, 0.03)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.375rem',
                })}
              >
                <div
                  className={css({
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  })}
                >
                  <span
                    className={css({ fontWeight: '600', fontSize: '0.875rem' })}
                  >
                    {room.name}
                  </span>
                  <span
                    className={css({
                      fontSize: '0.75rem',
                      color: 'rgba(255, 255, 255, 0.6)',
                      backgroundColor: 'rgba(255, 255, 255, 0.08)',
                      padding: '0.125rem 0.375rem',
                      borderRadius: '999px',
                    })}
                  >
                    {room.assignments.length}
                  </span>
                </div>

                {/* Assigned participant list */}
                {room.assignments.length > 0 ? (
                  <div
                    className={css({
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: '0.375rem',
                      marginTop: '0.25rem',
                    })}
                  >
                    {room.assignments.map((a) => (
                      <span
                        key={a.id}
                        className={css({
                          fontSize: '0.75rem',
                          backgroundColor: 'rgba(255, 255, 255, 0.06)',
                          padding: '0.125rem 0.375rem',
                          borderRadius: '0.25rem',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                        })}
                      >
                        {a.participant_name || a.participant_identity}
                        <button
                          onClick={() =>
                            handleManualAssign(
                              a.participant_identity,
                              a.participant_name || a.participant_identity,
                              null
                            )
                          }
                          aria-label="Unassign participant"
                          className={css({
                            border: 'none',
                            background: 'none',
                            color: 'rgba(255, 255, 255, 0.5)',
                            cursor: 'pointer',
                            padding: 0,
                            display: 'flex',
                            _hover: { color: 'white' },
                          })}
                        >
                          <RiCloseLine size={12} />
                        </button>
                      </span>
                    ))}
                  </div>
                ) : (
                  <div
                    className={css({
                      fontSize: '0.75rem',
                      color: 'rgba(255, 255, 255, 0.4)',
                    })}
                  >
                    {t('noParticipants')}
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* Participant Manual Assignment Section */}
          {assignableParticipants.length > 0 && (
            <div
              className={css({
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
                marginTop: '0.5rem',
                paddingTop: '0.75rem',
                borderTop: '1px solid',
                borderColor: 'box.border',
              })}
            >
              <div
                className={css({
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                })}
              >
                <span
                  className={css({ fontSize: '0.8125rem', fontWeight: '600' })}
                >
                  {t('assignParticipants') ?? 'Assign Participants'}
                </span>
                {unassignedCount > 0 ? (
                  <span
                    className={css({
                      fontSize: '0.75rem',
                      color: 'rgba(255, 255, 255, 0.5)',
                    })}
                  >
                    {t('unassigned', { count: unassignedCount })}
                  </span>
                ) : (
                  <span
                    className={css({
                      fontSize: '0.75rem',
                      color: '#18753c', // DSFR success green
                      fontWeight: '600',
                      backgroundColor: 'rgba(24, 117, 60, 0.12)',
                      padding: '0.125rem 0.375rem',
                      borderRadius: '999px',
                    })}
                  >
                    {t('allAssigned') ?? 'All participants assigned'}
                  </span>
                )}
              </div>

              {/* Participant list with room selector */}
              <div
                className={css({
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.375rem',
                  maxHeight: '160px',
                  overflowY: 'auto',
                })}
              >
                {assignableParticipants.map((p) => {
                  const assignedRoomId =
                    participantRoomMap.get(p.identity) ?? ''
                  return (
                    <div
                      key={p.identity}
                      className={css({
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.375rem 0.5rem',
                        borderRadius: '0.375rem',
                        backgroundColor: 'rgba(255, 255, 255, 0.02)',
                        fontSize: '0.8125rem',
                      })}
                    >
                      <div
                        className={css({
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.375rem',
                          overflow: 'hidden',
                        })}
                      >
                        <RiUserLine size={14} />
                        <span
                          className={css({
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          })}
                        >
                          {p.name || p.identity}
                        </span>
                      </div>

                      <select
                        value={assignedRoomId}
                        disabled={isAssigning}
                        onChange={(e) => {
                          const target = e.target.value || null
                          handleManualAssign(
                            p.identity,
                            p.name || p.identity,
                            target
                          )
                        }}
                        className={css({
                          padding: '0.25rem 0.5rem',
                          borderRadius: '0.25rem',
                          border: '1px solid',
                          borderColor: 'box.border',
                          backgroundColor: 'box.bg',
                          color: 'box.text',
                          fontSize: '0.75rem',
                        })}
                      >
                        <option value="">
                          {t('unassignedOption') ?? 'Unassigned'}
                        </option>
                        {session.breakout_rooms.map((room) => (
                          <option key={room.id} value={room.id}>
                            {room.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Randomize Button */}
          <div className={css({ display: 'flex', gap: '0.5rem' })}>
            <Button
              variant="secondaryText"
              size="sm"
              isDisabled={isRandomizing || assignableParticipants.length === 0}
              onPress={handleRandomize}
            >
              <RiShuffleLine size={16} />
              <span style={{ marginLeft: '0.25rem' }}>{t('randomize')}</span>
            </Button>
          </div>

          {/* Open All Rooms CTA */}
          <Button
            variant="primary"
            isDisabled={isActivating}
            onPress={handleActivate}
          >
            <RiPlayFill size={16} />
            <span style={{ marginLeft: '0.25rem' }}>{t('openAll')}</span>
          </Button>
        </>
      )}
    </div>
  )
}
