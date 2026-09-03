/**
 * Supervisory & Monitoring view for moderators during active breakout sessions.
 *
 * Features:
 * 1. Timer countdown (or elapsed time for open sessions).
 * 2. Broadcast announcement bar.
 * 3. Main Room Presence card showing attendees in the main room.
 * 4. Rich participant rosters per room with initials avatars.
 * 5. In-flight participant reassignment ('Move to...').
 * 6. Moderator 'Visit / Join' and 'Leave' room actions.
 * 7. 'Close All Rooms' recall button.
 */

import { useState, useCallback, useMemo } from 'react'
import { css } from '@/styled-system/css'
import { Button } from '@/primitives'
import { useTranslation } from 'react-i18next'
import { useSnapshot } from 'valtio'
import { useParticipants } from '@livekit/components-react'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutStatus } from '../api/useBreakoutStatus'
import { useUpdateBreakoutSession } from '../api/useUpdateBreakoutSession'
import { useBroadcastMessage } from '../api/useBroadcastMessage'
import { useAssignParticipants } from '../api/useAssignParticipants'
import { useBreakoutRoomSwap } from '../hooks/useBreakoutRoomSwap'
import { BreakoutTimer } from './BreakoutTimer'
import {
  RiStopFill,
  RiGroupLine,
  RiLoginBoxLine,
  RiArrowGoBackLine,
  RiMegaphoneLine,
  RiSendPlaneFill,
  RiHome4Line,
} from '@remixicon/react'

interface BreakoutActiveViewProps {
  roomUuid: string
}

const getInitials = (name: string): string => {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

export const BreakoutActiveView = ({ roomUuid }: BreakoutActiveViewProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.active' })
  const snap = useSnapshot(breakoutStore)
  const sessionId = snap.session?.id

  const [broadcastText, setBroadcastText] = useState('')
  const [broadcastSuccess, setBroadcastSuccess] = useState(false)

  // Live participants in current room (if host is in main room, these are main room attendees)
  const liveParticipants = useParticipants()

  const { data: statusData } = useBreakoutStatus(
    roomUuid,
    sessionId ?? undefined,
    !!sessionId
  )

  const { mutateAsync: updateSession, isPending: isClosing } =
    useUpdateBreakoutSession()

  const { mutateAsync: sendBroadcast, isPending: isBroadcasting } =
    useBroadcastMessage()

  const { mutateAsync: assignParticipants, isPending: isReassigning } =
    useAssignParticipants()

  const { moveToBreakoutRoom, returnToMainRoom } = useBreakoutRoomSwap({
    currentRoomSlug: snap.mainRoomSlug || '',
  })

  const handleCloseAll = useCallback(async () => {
    if (!sessionId) return

    await updateSession({
      roomId: roomUuid,
      sessionId,
      status: 'closed',
    })

    if (snap.currentBreakoutRoomLkName) {
      await returnToMainRoom()
    }
    clearBreakoutState()
  }, [
    sessionId,
    roomUuid,
    updateSession,
    snap.currentBreakoutRoomLkName,
    returnToMainRoom,
  ])

  const handleSendBroadcast = useCallback(async () => {
    if (!sessionId || !broadcastText.trim()) return

    await sendBroadcast({
      roomId: roomUuid,
      sessionId,
      message: broadcastText.trim(),
    })

    setBroadcastText('')
    setBroadcastSuccess(true)
    setTimeout(() => setBroadcastSuccess(false), 4000)
  }, [sessionId, roomUuid, broadcastText, sendBroadcast])

  // In-flight reassignment: move participant from current room to target room (or main room)
  const handleInFlightReassign = useCallback(
    async (
      participantIdentity: string,
      participantName: string,
      targetRoomId: string | null
    ) => {
      if (!sessionId || !snap.session) return

      const newAssignments: Record<
        string,
        { identity: string; name: string }[]
      > = {}

      for (const room of snap.session.breakout_rooms) {
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

      const result = await assignParticipants({
        roomId: roomUuid,
        sessionId,
        assignments: newAssignments,
      })

      breakoutStore.session = result
    },
    [sessionId, snap.session, roomUuid, assignParticipants]
  )

  const rooms = snap.session?.breakout_rooms ?? []

  // Map of active participants reported by LiveKit status endpoint
  const statusRoomMap = useMemo(() => {
    const map = new Map<
      string,
      { count: number; participants: { identity: string; name: string }[] }
    >()
    if (statusData?.rooms) {
      for (const r of statusData.rooms) {
        map.set(r.id, {
          count: r.participant_count,
          participants: r.participants,
        })
      }
    }
    return map
  }, [statusData])

  // Set of identities assigned to any breakout room
  const assignedIdentities = useMemo(() => {
    const set = new Set<string>()
    if (snap.session) {
      for (const r of snap.session.breakout_rooms) {
        for (const a of r.assignments) {
          set.add(a.participant_identity)
        }
      }
    }
    return set
  }, [snap.session])

  // Attendees currently unassigned or in main room
  const mainRoomAttendees = useMemo(() => {
    return liveParticipants.filter(
      (p) => !assignedIdentities.has(p.identity) && !p.isLocal
    )
  }, [liveParticipants, assignedIdentities])

  return (
    <div
      className={css({
        display: 'flex',
        flexDirection: 'column',
        gap: '0.875rem',
        padding: '0.875rem',
        overflowY: 'auto',
        flex: 1,
      })}
    >
      {/* Timer Header */}
      <div
        className={css({
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0.5rem',
        })}
      >
        <BreakoutTimer />
      </div>

      {/* Broadcast Announcement Bar */}
      <div
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
          padding: '0.75rem',
          borderRadius: '0.5rem',
          backgroundColor: 'rgba(255, 255, 255, 0.04)',
          border: '1px solid',
          borderColor: 'box.border',
        })}
      >
        <div
          className={css({
            display: 'flex',
            alignItems: 'center',
            gap: '0.375rem',
            fontSize: '0.8125rem',
            fontWeight: '600',
          })}
        >
          <RiMegaphoneLine size={16} />
          <span>{t('broadcastTitle') ?? 'Broadcast Announcement'}</span>
        </div>
        <div className={css({ display: 'flex', gap: '0.5rem' })}>
          <input
            type="text"
            value={broadcastText}
            onChange={(e) => setBroadcastText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSendBroadcast()
            }}
            placeholder={
              t('broadcastPlaceholder') ?? 'Type announcement to all rooms...'
            }
            className={css({
              flex: 1,
              padding: '0.375rem 0.625rem',
              borderRadius: '0.375rem',
              border: '1px solid',
              borderColor: 'box.border',
              backgroundColor: 'box.bg',
              color: 'box.text',
              fontSize: '0.8125rem',
            })}
          />
          <Button
            variant="primary"
            size="sm"
            isDisabled={isBroadcasting || !broadcastText.trim()}
            onPress={handleSendBroadcast}
            aria-label="Send broadcast"
          >
            <RiSendPlaneFill size={14} />
          </Button>
        </div>
        {broadcastSuccess && (
          <span
            className={css({
              fontSize: '0.75rem',
              color: 'success',
              fontWeight: '500',
            })}
          >
            {t('broadcastSent') ?? 'Announcement sent to all rooms!'}
          </span>
        )}
      </div>

      {/* Main Room Card */}
      <div
        className={css({
          padding: '0.75rem',
          borderRadius: '0.5rem',
          border: '1px solid',
          borderColor: !snap.currentBreakoutRoomLkName
            ? 'primary'
            : 'box.border',
          backgroundColor: !snap.currentBreakoutRoomLkName
            ? 'rgba(0, 0, 145, 0.06)'
            : 'rgba(255, 255, 255, 0.02)',
          display: 'flex',
          flexDirection: 'column',
          gap: '0.5rem',
        })}
      >
        <div
          className={css({
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          })}
        >
          <div
            className={css({
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            })}
          >
            <RiHome4Line size={16} />
            <span className={css({ fontWeight: '600', fontSize: '0.875rem' })}>
              {t('mainRoom') ?? 'Main Room'}
            </span>
            {!snap.currentBreakoutRoomLkName && (
              <span
                className={css({
                  fontSize: '0.6875rem',
                  padding: '0.125rem 0.375rem',
                  borderRadius: '999px',
                  backgroundColor: 'primary',
                  color: 'white',
                  fontWeight: '600',
                })}
              >
                {t('youAreHere') ?? 'You are here'}
              </span>
            )}
          </div>
          <span
            className={css({
              fontSize: '0.75rem',
              color: 'rgba(255, 255, 255, 0.6)',
              backgroundColor: 'rgba(255, 255, 255, 0.08)',
              padding: '0.125rem 0.375rem',
              borderRadius: '999px',
            })}
          >
            {mainRoomAttendees.length +
              (snap.currentBreakoutRoomLkName ? 0 : 1)}
          </span>
        </div>

        {/* Main room occupants with quick assign */}
        {mainRoomAttendees.length > 0 && (
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: '0.375rem',
              marginTop: '0.25rem',
              borderTop: '1px solid rgba(255, 255, 255, 0.06)',
              paddingTop: '0.375rem',
            })}
          >
            {mainRoomAttendees.map((p) => (
              <div
                key={p.identity}
                className={css({
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: '0.75rem',
                })}
              >
                <div
                  className={css({
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.375rem',
                  })}
                >
                  <span
                    className={css({
                      width: '18px',
                      height: '18px',
                      borderRadius: '999px',
                      backgroundColor: 'rgba(255, 255, 255, 0.1)',
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: '0.625rem',
                      fontWeight: '700',
                    })}
                  >
                    {getInitials(p.name || p.identity)}
                  </span>
                  <span>{p.name || p.identity}</span>
                </div>

                <select
                  disabled={isReassigning}
                  onChange={(e) => {
                    if (e.target.value) {
                      handleInFlightReassign(
                        p.identity,
                        p.name || p.identity,
                        e.target.value
                      )
                    }
                  }}
                  className={css({
                    padding: '0.125rem 0.375rem',
                    borderRadius: '0.25rem',
                    border: '1px solid',
                    borderColor: 'box.border',
                    backgroundColor: 'box.bg',
                    color: 'box.text',
                    fontSize: '0.6875rem',
                    cursor: isReassigning ? 'wait' : 'pointer',
                    opacity: isReassigning ? 0.6 : 1,
                  })}
                >
                  <option value="">{t('assignTo') ?? 'Assign to...'}</option>
                  {rooms.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Breakout Room Cards with Rich Participant Roster */}
      <div
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: '0.625rem',
        })}
      >
        {rooms.map((room) => {
          const liveData = statusRoomMap.get(room.id)
          const liveCount = liveData?.count ?? room.assignments.length
          const isCurrentRoom =
            snap.currentBreakoutRoomLkName === room.livekit_room_name

          // Assigned participants
          const participants = room.assignments

          return (
            <div
              key={room.id}
              className={css({
                padding: '0.75rem',
                borderRadius: '0.5rem',
                border: '1px solid',
                borderColor: isCurrentRoom ? '#000091' : 'box.border',
                backgroundColor: isCurrentRoom
                  ? 'rgba(0, 0, 145, 0.08)'
                  : 'rgba(255, 255, 255, 0.03)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.5rem',
              })}
            >
              {/* Room Card Header */}
              <div
                className={css({
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                })}
              >
                <div
                  className={css({
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  })}
                >
                  <span
                    className={css({ fontWeight: '600', fontSize: '0.875rem' })}
                  >
                    {room.name}
                  </span>
                  {isCurrentRoom && (
                    <span
                      className={css({
                        fontSize: '0.6875rem',
                        padding: '0.125rem 0.375rem',
                        borderRadius: '999px',
                        backgroundColor: 'primary',
                        color: 'white',
                        fontWeight: '600',
                      })}
                    >
                      {t('youAreHere') ?? 'You are here'}
                    </span>
                  )}
                </div>

                <div
                  className={css({
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                  })}
                >
                  <div
                    className={css({
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      fontSize: '0.8125rem',
                      color: 'rgba(255, 255, 255, 0.6)',
                    })}
                  >
                    <RiGroupLine size={14} />
                    <span>{liveCount}</span>
                  </div>

                  {/* Join / Leave Room Button */}
                  {isCurrentRoom ? (
                    <Button
                      variant="secondaryText"
                      size="sm"
                      onPress={returnToMainRoom}
                      aria-label={t('returnToMain')}
                    >
                      <RiArrowGoBackLine size={14} />
                      <span
                        className={css({
                          fontSize: '0.75rem',
                          marginLeft: '0.25rem',
                        })}
                      >
                        {t('leaveRoom') ?? 'Leave'}
                      </span>
                    </Button>
                  ) : (
                    <Button
                      variant="secondaryText"
                      size="sm"
                      onPress={() => {
                        if (sessionId) {
                          moveToBreakoutRoom(
                            room.id,
                            sessionId,
                            roomUuid,
                            room.name
                          )
                        }
                      }}
                      aria-label={t('visitRoom')}
                    >
                      <RiLoginBoxLine size={14} />
                      <span
                        className={css({
                          fontSize: '0.75rem',
                          marginLeft: '0.25rem',
                        })}
                      >
                        {t('visitRoom') ?? 'Visit'}
                      </span>
                    </Button>
                  )}
                </div>
              </div>

              {/* Expandable / Visible Participant Roster with In-Flight Move Selector */}
              {participants.length > 0 ? (
                <div
                  className={css({
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.375rem',
                    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                    paddingTop: '0.5rem',
                  })}
                >
                  {participants.map((a) => (
                    <div
                      key={a.id}
                      className={css({
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        padding: '0.25rem 0.375rem',
                        borderRadius: '0.375rem',
                        backgroundColor: 'rgba(255, 255, 255, 0.02)',
                        fontSize: '0.75rem',
                      })}
                    >
                      <div
                        className={css({
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.375rem',
                          minWidth: 0,
                          flex: 1,
                        })}
                      >
                        <span
                          className={css({
                            width: '20px',
                            height: '20px',
                            borderRadius: '999px',
                            backgroundColor: 'rgba(255, 255, 255, 0.12)',
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '0.625rem',
                            fontWeight: '700',
                            flexShrink: 0,
                          })}
                        >
                          {getInitials(
                            a.participant_name || a.participant_identity
                          )}
                        </span>
                        <span
                          className={css({
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          })}
                        >
                          {a.participant_name || a.participant_identity}
                        </span>
                      </div>

                      {/* In-Flight Reassign Selector */}
                      <select
                        value={room.id}
                        disabled={isReassigning}
                        onChange={(e) => {
                          const target = e.target.value || null
                          handleInFlightReassign(
                            a.participant_identity,
                            a.participant_name || a.participant_identity,
                            target
                          )
                        }}
                        className={css({
                          padding: '0.125rem 0.375rem',
                          borderRadius: '0.25rem',
                          border: '1px solid',
                          borderColor: 'box.border',
                          backgroundColor: 'box.bg',
                          color: 'box.text',
                          fontSize: '0.6875rem',
                          marginLeft: '0.5rem',
                          flexShrink: 0,
                        })}
                      >
                        <option value="">
                          {t('returnToMain') ?? 'Main Room'}
                        </option>
                        {rooms.map((targetR) => (
                          <option key={targetR.id} value={targetR.id}>
                            {targetR.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  className={css({
                    fontSize: '0.75rem',
                    color: 'rgba(255, 255, 255, 0.4)',
                    borderTop: '1px solid rgba(255, 255, 255, 0.06)',
                    paddingTop: '0.375rem',
                  })}
                >
                  {t('noParticipants') ?? 'No participants in this room'}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Close All button */}
      <Button
        variant="danger"
        isDisabled={isClosing}
        onPress={handleCloseAll}
        className={css({ marginTop: 'auto' })}
      >
        <RiStopFill size={16} />
        <span style={{ marginLeft: '0.25rem' }}>{t('closeAll')}</span>
      </Button>
    </div>
  )
}
