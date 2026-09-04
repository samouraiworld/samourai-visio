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
import { useRetryBreakoutSession } from '../api/useRetryBreakoutSession'
import { ApiError } from '@/api/ApiError'
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

export const BreakoutSetup = ({ roomUuid, session }: BreakoutSetupProps) => {
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
  const { mutateAsync: retrySession, isPending: isRetrying } =
    useRetryBreakoutSession()

  // Eligible participants (exclude local host)
  const assignableParticipants = useMemo(
    () => participants.filter((p) => !p.isLocal),
    [participants]
  )

  const handleCreate = useCallback(async () => {
    try {
      await createSession({
        roomId: roomUuid,
        numRooms,
        durationSeconds: duration === '0' ? null : parseInt(duration, 10),
      })
    } catch (e) {
      if (e instanceof ApiError && e.statusCode === 409) {
        // A session already exists (e.g. host reloaded the tab mid-session).
        // useBreakoutSession polling will surface it within its next interval.
        return
      }
      throw e
    }
  }, [roomUuid, numRooms, duration, createSession])

  const handleRandomize = useCallback(async () => {
    if (!session) return

    const participantList = assignableParticipants.map((p) => ({
      identity: p.identity,
      name: p.name ?? p.identity,
    }))

    await randomize({
      roomId: roomUuid,
      sessionId: session.id,
      revision: session.revision,
      participants: participantList,
    })
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

      await assignManual({
        roomId: roomUuid,
        sessionId: session.id,
        revision: session.revision,
        assignments: newAssignments,
      })
    },
    [session, roomUuid, assignManual]
  )

  const handleActivate = useCallback(async () => {
    if (!session) return

    await updateSession({
      roomId: roomUuid,
      sessionId: session.id,
      status: 'active',
    })
  }, [session, roomUuid, updateSession])

  const handleRetry = useCallback(async () => {
    if (!session) return
    await retrySession({ roomId: roomUuid, sessionId: session.id })
  }, [retrySession, roomUuid, session])

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
        gap: 1,
        padding: 1,
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
              gap: 0.5,
            })}
          >
            <label className={css({ fontSize: 14, fontWeight: '500' })}>
              {t('roomCount')}
            </label>
            <div
              className={css({
                display: 'flex',
                gap: 0.5,
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
                  aria-label={t('roomCountOption', { count: n })}
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
              gap: 0.5,
            })}
          >
            <label className={css({ fontSize: 14, fontWeight: '500' })}>
              {t('duration')}
            </label>
            <select
              value={duration}
              onChange={(e) => setDuration(e.target.value)}
              aria-label={t('duration')}
              className={css({
                paddingBlock: 0.5,
                paddingInline: 0.75,
                borderRadius: '6',
                borderWidth: 1,
                borderStyle: 'solid',
                borderColor: 'box.border',
                backgroundColor: 'box.bg',
                color: 'box.text',
                fontSize: 14,
                cursor: 'pointer',
                outline: 'none',
                _focus: {
                  borderColor: 'primary',
                  outlineWidth: 2,
                  outlineStyle: 'solid',
                  outlineColor: 'focusRing',
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
            {t('create')}
          </Button>
        </>
      )}

      {session?.effect_error && (
        <div
          role="alert"
          className={css({
            display: 'flex',
            flexDirection: 'column',
            gap: 0.5,
            padding: 0.75,
            borderRadius: '8',
            backgroundColor: 'danger.subtle',
            color: 'danger.subtle-text',
          })}
        >
          <span>{t('syncFailed')}</span>
          <Button
            variant="secondaryText"
            size="sm"
            isDisabled={isRetrying}
            onPress={handleRetry}
          >
            {t('retrySynchronization')}
          </Button>
        </div>
      )}

      {session?.status === 'activating' && !session.effect_error && (
        <div role="status">{t('synchronizing')}</div>
      )}

      {session && session.status === 'configuring' && (
        <>
          {/* Room Cards List */}
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: 0.625,
            })}
          >
            {session.breakout_rooms.map((room) => (
              <div
                key={room.id}
                className={css({
                  padding: 0.75,
                  borderRadius: '8',
                  borderWidth: 1,
                  borderStyle: 'solid',
                  borderColor: 'box.border',
                  backgroundColor: 'box.bg',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.375,
                })}
              >
                <div
                  className={css({
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  })}
                >
                  <span className={css({ fontWeight: '600', fontSize: 14 })}>
                    {room.name}
                  </span>
                  <span
                    className={css({
                      fontSize: 12,
                      color: 'control.text',
                      backgroundColor: 'control',
                      paddingBlock: 0.125,
                      paddingInline: 0.375,
                      borderRadius: 'full',
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
                      gap: 0.375,
                      marginTop: 0.25,
                    })}
                  >
                    {room.assignments.map((a) => (
                      <span
                        key={a.id}
                        className={css({
                          fontSize: 12,
                          backgroundColor: 'control',
                          paddingBlock: 0.125,
                          paddingInline: 0.375,
                          borderRadius: '4',
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 0.25,
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
                          aria-label={t('unassignParticipant', {
                            name: a.participant_name || a.participant_identity,
                          })}
                          className={css({
                            border: 'none',
                            background: 'none',
                            color: 'control.text',
                            cursor: 'pointer',
                            padding: 0,
                            display: 'flex',
                            _hover: { color: 'control.text' },
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
                      fontSize: 12,
                      color: 'control.text',
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
                gap: 0.5,
                marginTop: 0.5,
                paddingTop: 0.75,
                borderTopWidth: 1,
                borderTopStyle: 'solid',
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
                <span className={css({ fontSize: 12, fontWeight: '600' })}>
                  {t('assignParticipants')}
                </span>
                {unassignedCount > 0 ? (
                  <span
                    className={css({
                      fontSize: 12,
                      color: 'control.text',
                    })}
                  >
                    {t('unassigned', { count: unassignedCount })}
                  </span>
                ) : (
                  <span
                    className={css({
                      fontSize: 12,
                      color: 'success.subtle-text',
                      fontWeight: '600',
                      backgroundColor: 'success.subtle',
                      paddingBlock: 0.125,
                      paddingInline: 0.375,
                      borderRadius: 'full',
                    })}
                  >
                    {t('allAssigned')}
                  </span>
                )}
              </div>

              {/* Participant list with room selector */}
              <div
                className={css({
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 0.375,
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
                        paddingBlock: 0.375,
                        paddingInline: 0.5,
                        borderRadius: '6',
                        backgroundColor: 'box.bg',
                        fontSize: 12,
                      })}
                    >
                      <div
                        className={css({
                          display: 'flex',
                          alignItems: 'center',
                          gap: 0.375,
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
                        aria-label={t('assignParticipant', {
                          name: p.name || p.identity,
                        })}
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
                          paddingBlock: 0.25,
                          paddingInline: 0.5,
                          borderRadius: '4',
                          borderWidth: 1,
                          borderStyle: 'solid',
                          borderColor: 'box.border',
                          backgroundColor: 'box.bg',
                          color: 'box.text',
                          fontSize: 12,
                        })}
                      >
                        <option value="">{t('unassignedOption')}</option>
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
          <div className={css({ display: 'flex', gap: 0.5 })}>
            <Button
              variant="secondaryText"
              size="sm"
              isDisabled={isRandomizing || assignableParticipants.length === 0}
              onPress={handleRandomize}
            >
              <RiShuffleLine size={16} />
              <span className={css({ marginLeft: 0.25 })}>
                {t('randomize')}
              </span>
            </Button>
          </div>

          {/* Open All Rooms CTA */}
          <Button
            variant="primary"
            isDisabled={isActivating || !!session.effect_error}
            onPress={handleActivate}
          >
            <RiPlayFill size={16} />
            <span className={css({ marginLeft: 0.25 })}>{t('openAll')}</span>
          </Button>
        </>
      )}
    </div>
  )
}
