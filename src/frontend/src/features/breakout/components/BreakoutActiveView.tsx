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
import { useRetryBreakoutSession } from '../api/useRetryBreakoutSession'
import { useBroadcastMessage } from '../api/useBroadcastMessage'
import { useAssignParticipants } from '../api/useAssignParticipants'
import { useBreakoutRoomSwap } from '../hooks/useBreakoutRoomSwap'
import { BreakoutTimer } from './BreakoutTimer'
import type { BreakoutSession } from '../api/types'
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
  session: BreakoutSession
}

const getInitials = (name: string): string => {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return name.slice(0, 2).toUpperCase()
}

export const BreakoutActiveView = ({
  roomUuid,
  session,
}: BreakoutActiveViewProps) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.active' })
  const snap = useSnapshot(breakoutStore)
  const sessionId = session.id

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
  const { mutateAsync: retrySession, isPending: isRetrying } =
    useRetryBreakoutSession()

  const { mutateAsync: sendBroadcast, isPending: isBroadcasting } =
    useBroadcastMessage()

  const { mutateAsync: assignParticipants, isPending: isReassigning } =
    useAssignParticipants()

  const { moveToBreakoutRoom, returnToMainRoom, returnToMainRoomAfterClose } =
    useBreakoutRoomSwap({
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
      await returnToMainRoomAfterClose()
      return
    }
    clearBreakoutState()
  }, [
    sessionId,
    roomUuid,
    updateSession,
    snap.currentBreakoutRoomLkName,
    returnToMainRoomAfterClose,
  ])

  const handleRetry = useCallback(async () => {
    await retrySession({ roomId: roomUuid, sessionId })
  }, [retrySession, roomUuid, sessionId])

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
      if (!sessionId) return

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

      await assignParticipants({
        roomId: roomUuid,
        sessionId,
        revision: session.revision,
        assignments: newAssignments,
      })
    },
    [sessionId, session, roomUuid, assignParticipants]
  )

  const rooms = session.breakout_rooms

  // Map of active participants reported by LiveKit status endpoint
  const statusRoomMap = useMemo(() => {
    const map = new Map<
      string,
      {
        count: number | null
        participants: { identity: string; name: string }[]
      }
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

  const localIdentity = liveParticipants.find(
    (participant) => participant.isLocal
  )?.identity

  // Actual main-room presence is reported by the backend, independent of assignment.
  const mainRoomAttendees = useMemo(() => {
    return (statusData?.main_room.participants ?? []).filter(
      (participant) => participant.identity !== localIdentity
    )
  }, [localIdentity, statusData?.main_room.participants])

  if (session.status === 'closing') {
    return (
      <div
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: 0.75,
          padding: 0.75,
          flex: 1,
        })}
      >
        {session.effect_error ? (
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
        ) : (
          <div role="status">{t('closing')}</div>
        )}
      </div>
    )
  }

  return (
    <div
      className={css({
        display: 'flex',
        flexDirection: 'column',
        gap: 0.75,
        padding: 0.75,
        overflowY: 'auto',
        flex: 1,
      })}
    >
      {session.effect_error && (
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

      {/* Timer Header */}
      <div
        className={css({
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 0.5,
        })}
      >
        <BreakoutTimer timing={session} />
      </div>

      {/* Broadcast Announcement Bar */}
      <div
        className={css({
          display: 'flex',
          flexDirection: 'column',
          gap: 0.5,
          padding: 0.75,
          borderRadius: '8',
          backgroundColor: 'box.bg',
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: 'box.border',
        })}
      >
        <div
          className={css({
            display: 'flex',
            alignItems: 'center',
            gap: 0.375,
            fontSize: 12,
            fontWeight: '600',
          })}
        >
          <RiMegaphoneLine size={16} />
          <span>{t('broadcastTitle')}</span>
        </div>
        <div className={css({ display: 'flex', gap: 0.5, flexWrap: 'wrap' })}>
          <input
            type="text"
            value={broadcastText}
            onChange={(e) => setBroadcastText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSendBroadcast()
            }}
            placeholder={t('broadcastPlaceholder')}
            className={css({
              flex: 1,
              paddingBlock: 0.375,
              paddingInline: 0.625,
              borderRadius: '6',
              borderWidth: 1,
              borderStyle: 'solid',
              borderColor: 'box.border',
              backgroundColor: 'box.bg',
              color: 'box.text',
              fontSize: 12,
              minWidth: 0,
            })}
          />
          <Button
            variant="primary"
            size="sm"
            isDisabled={isBroadcasting || !broadcastText.trim()}
            onPress={handleSendBroadcast}
            aria-label={t('sendBroadcast')}
          >
            <RiSendPlaneFill size={14} />
          </Button>
        </div>
        {broadcastSuccess && (
          <span
            className={css({
              fontSize: 12,
              color: 'success',
              fontWeight: '500',
            })}
          >
            {t('broadcastSent')}
          </span>
        )}
      </div>

      {/* Main Room Card */}
      <div
        className={css({
          padding: 0.75,
          borderRadius: '8',
          borderWidth: 1,
          borderStyle: 'solid',
          borderColor: !snap.currentBreakoutRoomLkName
            ? 'primary'
            : 'box.border',
          backgroundColor: !snap.currentBreakoutRoomLkName
            ? 'primary.subtle'
            : 'box.bg',
          display: 'flex',
          flexDirection: 'column',
          gap: 0.5,
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
              gap: 0.5,
            })}
          >
            <RiHome4Line size={16} />
            <span className={css({ fontWeight: '600', fontSize: 14 })}>
              {t('mainRoom')}
            </span>
            {!snap.currentBreakoutRoomLkName && (
              <span
                className={css({
                  fontSize: 10,
                  paddingBlock: 0.125,
                  paddingInline: 0.375,
                  borderRadius: 'full',
                  backgroundColor: 'primary',
                  color: 'primary.text',
                  fontWeight: '600',
                })}
              >
                {t('youAreHere')}
              </span>
            )}
          </div>
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
            {statusData?.main_room.participant_count === null ||
            statusData?.main_room.participant_count === undefined
              ? t('statusUnknown')
              : statusData.main_room.participant_count}
          </span>
        </div>

        {/* Main room occupants with quick assign */}
        {mainRoomAttendees.length > 0 && (
          <div
            className={css({
              display: 'flex',
              flexDirection: 'column',
              gap: 0.375,
              marginTop: 0.25,
              borderTopWidth: 1,
              borderTopStyle: 'solid',
              borderTopColor: 'box.border',
              paddingTop: 0.375,
            })}
          >
            {mainRoomAttendees.map((p) => (
              <div
                key={p.identity}
                className={css({
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: 12,
                })}
              >
                <div
                  className={css({
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.375,
                  })}
                >
                  <span
                    className={css({
                      width: 1.25,
                      height: 1.25,
                      borderRadius: 'full',
                      backgroundColor: 'control',
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 10,
                      fontWeight: '700',
                    })}
                  >
                    {getInitials(p.name || p.identity)}
                  </span>
                  <span>{p.name || p.identity}</span>
                </div>

                <select
                  aria-label={t('reassignParticipant', {
                    name: p.name || p.identity,
                  })}
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
                    paddingBlock: 0.125,
                    paddingInline: 0.375,
                    borderRadius: '4',
                    borderWidth: 1,
                    borderStyle: 'solid',
                    borderColor: 'box.border',
                    backgroundColor: 'box.bg',
                    color: 'box.text',
                    fontSize: 10,
                    cursor: isReassigning ? 'wait' : 'pointer',
                    opacity: isReassigning ? 0.6 : 1,
                  })}
                >
                  <option value="">{t('assignTo')}</option>
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
          gap: 0.625,
        })}
      >
        {rooms.map((room) => {
          const liveData = statusRoomMap.get(room.id)
          const liveCount = liveData?.count
          const isCurrentRoom =
            snap.currentBreakoutRoomLkName === room.livekit_room_name

          // Actual presence is distinct from the configured assignment list.
          const participants = liveData?.participants ?? []

          return (
            <div
              key={room.id}
              className={css({
                padding: 0.75,
                borderRadius: '8',
                borderWidth: 1,
                borderStyle: 'solid',
                borderColor: isCurrentRoom ? 'primary' : 'box.border',
                backgroundColor: isCurrentRoom ? 'primary.subtle' : 'box.bg',
                display: 'flex',
                flexDirection: 'column',
                gap: 0.5,
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
                    gap: 0.5,
                  })}
                >
                  <span className={css({ fontWeight: '600', fontSize: 14 })}>
                    {room.name}
                  </span>
                  {isCurrentRoom && (
                    <span
                      className={css({
                        fontSize: 10,
                        paddingBlock: 0.125,
                        paddingInline: 0.375,
                        borderRadius: 'full',
                        backgroundColor: 'primary',
                        color: 'primary.text',
                        fontWeight: '600',
                      })}
                    >
                      {t('youAreHere')}
                    </span>
                  )}
                </div>

                <div
                  className={css({
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                  })}
                >
                  <div
                    className={css({
                      display: 'flex',
                      alignItems: 'center',
                      gap: 0.25,
                      fontSize: 12,
                      color: 'control.text',
                    })}
                  >
                    <RiGroupLine size={14} />
                    <span>
                      {liveCount === null || liveCount === undefined
                        ? t('statusUnknown')
                        : liveCount}
                    </span>
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
                          fontSize: 12,
                          marginLeft: 0.25,
                        })}
                      >
                        {t('leaveRoom')}
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
                            room.name,
                            true
                          )
                        }
                      }}
                      aria-label={t('visitRoom')}
                    >
                      <RiLoginBoxLine size={14} />
                      <span
                        className={css({
                          fontSize: 12,
                          marginLeft: 0.25,
                        })}
                      >
                        {t('visitRoom')}
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
                    gap: 0.375,
                    borderTopWidth: 1,
                    borderTopStyle: 'solid',
                    borderTopColor: 'box.border',
                    paddingTop: 0.5,
                  })}
                >
                  {participants.map((a) => (
                    <div
                      key={a.identity}
                      className={css({
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        paddingBlock: 0.25,
                        paddingInline: 0.375,
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
                          minWidth: 0,
                          flex: 1,
                        })}
                      >
                        <span
                          className={css({
                            width: 1.25,
                            height: 1.25,
                            borderRadius: 'full',
                            backgroundColor: 'control',
                            display: 'inline-flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: 10,
                            fontWeight: '700',
                            flexShrink: 0,
                          })}
                        >
                          {getInitials(a.name || a.identity)}
                        </span>
                        <span
                          className={css({
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          })}
                        >
                          {a.name || a.identity}
                        </span>
                      </div>

                      {/* In-Flight Reassign Selector */}
                      <select
                        aria-label={t('reassignParticipant', {
                          name: a.name || a.identity,
                        })}
                        value={room.id}
                        disabled={isReassigning}
                        onChange={(e) => {
                          const target = e.target.value || null
                          handleInFlightReassign(
                            a.identity,
                            a.name || a.identity,
                            target
                          )
                        }}
                        className={css({
                          paddingBlock: 0.125,
                          paddingInline: 0.375,
                          borderRadius: '4',
                          borderWidth: 1,
                          borderStyle: 'solid',
                          borderColor: 'box.border',
                          backgroundColor: 'box.bg',
                          color: 'box.text',
                          fontSize: 10,
                          marginLeft: 0.5,
                          flexShrink: 0,
                        })}
                      >
                        <option value="">{t('returnToMain')}</option>
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
                    fontSize: 12,
                    color: 'control.text',
                    borderTopWidth: 1,
                    borderTopStyle: 'solid',
                    borderTopColor: 'box.border',
                    paddingTop: 0.375,
                  })}
                >
                  {t('noParticipants')}
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
        <span className={css({ marginLeft: 0.25 })}>{t('closeAll')}</span>
      </Button>
    </div>
  )
}
