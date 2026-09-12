import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import {
  LiveKitRoom,
  useRoomContext,
  usePersistentUserChoices,
} from '@livekit/components-react'
import {
  ConnectionError,
  ConnectionErrorReason,
  DisconnectReason,
  MediaDeviceFailure,
  Room,
  type RoomOptions,
  VideoPresets,
} from 'livekit-client'
import { getMediaDeviceFailure } from '@/features/rooms/livekit/utils/mediaPermissions'
import { keys } from '@/api/queryKeys'
import { queryClient } from '@/api/queryClient'
import { Screen } from '@/layout/Screen'
import { QueryAware } from '@/components/QueryAware'
import { ErrorScreen } from '@/components/ErrorScreen'
import { fetchRoom } from '../api/fetchRoom'
import type { ApiRoom } from '../api/ApiRoom'
import { useCreateRoom } from '../api/createRoom'
import { InviteDialog } from './InviteDialog'
import { VideoConference } from '../livekit/prefabs/VideoConference'
import { css } from '@/styled-system/css'
import { BackgroundProcessorFactory } from '../livekit/components/blur'
import { LocalUserChoices } from '@/stores/userChoices'
import {
  captureEvent,
  captureMediaEvent,
  reportError,
} from '@/features/analytics/telemetry'
import { useConfig } from '@/api/useConfig'
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'
import { isFireFox } from '@/utils/livekit'
import { useIsMobile } from '@/utils/useIsMobile'
import { navigateTo } from '@/navigation/navigateTo'
import { PictureInPictureConference } from '@/features/pip/components/PictureInPictureConference'
import { notifyAutoMutedOnJoin } from '@/features/notifications/utils'
import { useSnapshot } from 'valtio'
import { userPreferencesStore } from '@/stores/userPreferences'
import { userStore } from '@/stores/user'
import { WatchMediaDeviceErrors } from './WatchMediaDeviceErrors'
import { MeetDevtools } from '@/features/devtools'
import { VOICE_AUDIO_CONSTRAINTS } from '@/features/rooms/livekit/utils/constants'
import {
  bindBreakoutToMainRoom,
  breakoutStore,
  clearBreakoutState,
  clearMatchingPendingHelpAcknowledgement,
  completeBreakoutTransition,
  failBreakoutConnection,
  registerRoomSwapHandler,
} from '@/features/breakout/stores/breakout'
import { BreakoutTransition } from '@/features/breakout/components/BreakoutTransition'
import { BreakoutParticipantOverlay } from '@/features/breakout/components/BreakoutParticipantOverlay'
import { BreakoutRecallBanner } from '@/features/breakout/components/BreakoutRecallBanner'
import { BreakoutBroadcastBanner } from '@/features/breakout/components/BreakoutBroadcastBanner'
import { BreakoutHelpAlertBanner } from '@/features/breakout/components/BreakoutHelpAlertBanner'
import { useBreakoutMetadataWatcher } from '@/features/breakout/hooks/useBreakoutMetadataWatcher'
import { useBreakoutDataMessages } from '@/features/breakout/hooks/useBreakoutDataMessages'
import { useBreakoutRoomSwap } from '@/features/breakout/hooks/useBreakoutRoomSwap'
import {
  acknowledgeBreakoutHelp,
  breakoutHelpRequestsKey,
  useAcknowledgeBreakoutHelp,
  useBreakoutHelpRequests,
} from '@/features/breakout/api/useBreakoutHelpRequests'
import {
  fetchCurrentBreakoutAssignment,
  useCurrentBreakoutAssignment,
} from '@/features/breakout/api/useCurrentBreakoutAssignment'
import {
  isRemovalAReassignment,
  resolveDisconnectAction,
} from '@/features/breakout/utils/disconnectActions'
import { useBreakoutRecovery } from '@/features/breakout/hooks/useBreakoutRecovery'
import { finishBreakoutConnection } from '@/features/breakout/utils/connectionLifecycle'
import { acknowledgeConnectedHelp } from '@/features/breakout/utils/helpAcknowledgement'

const BreakoutWatcher = ({
  currentRoomSlug,
  setActiveRoomConnection,
  mainRoomId,
}: {
  currentRoomSlug: string
  setActiveRoomConnection: (conn: { token: string; roomName: string }) => void
  mainRoomId: string
}) => {
  useBreakoutMetadataWatcher({
    currentRoomSlug,
    setActiveRoomConnection,
    mainRoomId,
  })
  useBreakoutDataMessages()
  return null
}

/**
 * Inner component rendered inside <LiveKitRoom> that owns the hooks requiring
 * a room provider context (useLocalParticipant via useBreakoutRoomSwap) and
 * the overlays driven by those hooks.
 *
 * Must NOT be called at Conference component scope — it would be above
 * <LiveKitRoom> in the render tree and throw: "No room provided".
 */
const BreakoutActions = ({
  roomId,
  setActiveRoomConnection,
  mainRoomId,
}: {
  roomId: string
  setActiveRoomConnection: (conn: { token: string; roomName: string }) => void
  mainRoomId: string
}) => {
  const { t } = useTranslation('rooms', {
    keyPrefix: 'breakout.participant',
  })
  const { returnToMainRoom, moveToBreakoutRoom } = useBreakoutRoomSwap({
    currentRoomSlug: roomId,
    setActiveRoomConnection,
  })
  const snap = useSnapshot(breakoutStore)
  const connectedRoom = useRoomContext()
  const isAdminOrOwner = useIsAdminOrOwner()
  // Breakout tokens are minted with role "member"; keep the host's controls
  // while they visit a room.
  const canManageBreakout = isAdminOrOwner || snap.isModeratorVisiting
  const { data: helpRequests = [] } = useBreakoutHelpRequests(
    mainRoomId,
    snap.activeSessionId ?? undefined,
    canManageBreakout
  )
  const { mutate: acknowledgeHelp } = useAcknowledgeBreakoutHelp()
  const helpRequest = helpRequests[0]
  const { data: assignmentState } = useCurrentBreakoutAssignment(
    mainRoomId,
    snap.activeSessionId ?? undefined
  )

  const handleAcknowledge = () => {
    if (!snap.activeSessionId || !helpRequest) return
    breakoutStore.pendingHelpAcknowledgement = null
    acknowledgeHelp({
      roomId: mainRoomId,
      sessionId: snap.activeSessionId,
      helpRequestId: helpRequest.id,
      expectedBreakoutRoomId: helpRequest.breakout_room,
      expectedAssignmentRevision: helpRequest.assignment_revision,
    })
  }
  return (
    <>
      {snap.activeSessionId && snap.assignedRoomId && (
        <BreakoutRecallBanner
          onRecall={returnToMainRoom}
          timing={assignmentState}
          canRecall={!!snap.currentBreakoutRoomLkName}
        />
      )}
      <div
        className={css({
          position: 'absolute',
          top: 0.75,
          insetInline: 0,
          marginInline: 'auto',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 0.625,
          width: 'full',
          maxWidth: 'room-side-panel',
          zIndex: 100,
          pointerEvents: 'none',
        })}
      >
        {snap.activeSessionId && snap.assignedRoomId && (
          <BreakoutParticipantOverlay
            roomId={mainRoomId}
            onReturnToMain={returnToMainRoom}
            onReturnToAssigned={() => {
              const assignment = assignmentState?.assignment
              if (!assignment || !snap.activeSessionId) return
              void moveToBreakoutRoom(
                assignment.breakout_room_id,
                snap.activeSessionId,
                mainRoomId,
                assignment.breakout_room_name
              ).catch(() => undefined)
            }}
          />
        )}
        {snap.transitionError && !snap.assignedRoomId && (
          <div
            role="alert"
            className={css({
              pointerEvents: 'auto',
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
        {snap.broadcastAnnouncement && (
          <BreakoutBroadcastBanner
            message={snap.broadcastAnnouncement.message}
            onDismiss={() => {
              breakoutStore.broadcastAnnouncement = null
            }}
          />
        )}
      </div>
      {helpRequest && (
        <BreakoutHelpAlertBanner
          roomName={helpRequest.breakout_room_name}
          participantName={helpRequest.requester_name}
          onJoinRoom={() => {
            void moveToBreakoutRoom(
              helpRequest.breakout_room,
              helpRequest.session,
              mainRoomId,
              helpRequest.breakout_room_name,
              true
            )
              .then((expectedLivekitRoomName) => {
                if (
                  connectedRoom.state === 'connected' &&
                  connectedRoom.name === expectedLivekitRoomName
                ) {
                  handleAcknowledge()
                  return
                }
                breakoutStore.pendingHelpAcknowledgement = {
                  roomId: mainRoomId,
                  sessionId: helpRequest.session,
                  helpRequestId: helpRequest.id,
                  expectedBreakoutRoomId: helpRequest.breakout_room,
                  expectedLivekitRoomName,
                  assignmentRevision: helpRequest.assignment_revision,
                }
              })
              .catch(() => undefined)
          }}
          onDismiss={handleAcknowledge}
        />
      )}
    </>
  )
}

export const Conference = ({
  roomId,
  initialRoomData,
  mode = 'join',
}: {
  roomId: string
  mode?: 'join' | 'create'
  initialRoomData?: ApiRoom
}) => {
  const { data: apiConfig } = useConfig()

  const { userChoices: userConfig } = usePersistentUserChoices() as {
    userChoices: LocalUserChoices
  }
  const breakoutSnap = useSnapshot(breakoutStore)

  const { username } = useSnapshot(userStore)

  useEffect(() => {
    void captureMediaEvent('visit-room', { slug: roomId })
  }, [roomId])
  const fetchKey = [keys.room, roomId]

  const [isConnectionWarmedUp, setIsConnectionWarmedUp] = useState(false)

  const userPreferencesSnap = useSnapshot(userPreferencesStore)

  const {
    mutateAsync: createRoom,
    status: createStatus,
    isError: isCreateError,
  } = useCreateRoom({
    onSuccess: (data) => {
      queryClient.setQueryData(fetchKey, data)
    },
  })

  const {
    status: fetchStatus,
    isError: isFetchError,
    data,
  } = useQuery({
    queryKey: fetchKey,
    staleTime: 6 * 60 * 60 * 1000, // By default, LiveKit access tokens expire 6 hours after generation
    initialData: initialRoomData,
    queryFn: () =>
      fetchRoom({
        roomId: roomId as string,
        username: username,
      }).catch((error) => {
        if (error.statusCode == '404') {
          createRoom({ slug: roomId, username })
        }
      }),
    retry: false,
  })

  // ── Breakout rooms: in-component room swap ──
  const [activeRoomConnection, setRoomConnectionState] = useState<{
    token: string | undefined
    roomName: string | undefined
    attempt: number
  }>({ token: undefined, roomName: undefined, attempt: 0 })

  const setActiveRoomConnection = useCallback(
    (connection: { token: string; roomName: string }) => {
      setRoomConnectionState((previous) => ({
        ...connection,
        attempt: previous.attempt + 1,
      }))
    },
    []
  )

  useEffect(() => {
    return registerRoomSwapHandler(setActiveRoomConnection)
  }, [setActiveRoomConnection])

  // Sync initial token from API data
  useEffect(() => {
    if (data?.livekit && !activeRoomConnection.token) {
      const initialConnection = data.livekit
      setRoomConnectionState((previous) =>
        previous.token
          ? previous
          : {
              token: initialConnection.token,
              roomName: initialConnection.room,
              attempt: previous.attempt,
            }
      )
    }
  }, [data?.livekit, activeRoomConnection.token])

  // Sync main room UUID and slug into breakout store
  useEffect(() => {
    if (data?.id) {
      bindBreakoutToMainRoom(data.id, roomId)
    }
  }, [data?.id, roomId])

  // NOTE: useBreakoutRoomSwap is intentionally NOT called here.
  // It calls useLocalParticipant() internally, which requires a LiveKit room
  // provider context. This hook is called inside <BreakoutActions> below,
  // which is rendered inside <LiveKitRoom>.

  const roomOptions = useMemo((): RoomOptions => {
    return {
      adaptiveStream: true,
      dynacast: true,
      publishDefaults: {
        videoCodec: 'vp9',
      },
      videoCaptureDefaults: {
        deviceId: userConfig.videoDeviceId ?? undefined,
        resolution: userConfig.videoPublishResolution
          ? VideoPresets[userConfig.videoPublishResolution].resolution
          : undefined,
      },
      audioCaptureDefaults: {
        deviceId: userConfig.audioDeviceId ?? undefined,
        ...VOICE_AUDIO_CONSTRAINTS,
      },
      audioOutput: {
        deviceId: userConfig.audioOutputDeviceId ?? undefined,
      },
    }
    // do not rely on the userConfig object directly as its reference may change on every render
  }, [
    userConfig.videoDeviceId,
    userConfig.videoPublishResolution,
    userConfig.audioDeviceId,
    userConfig.audioOutputDeviceId,
  ])

  // Each attempt gets its own transport, even when same-second JWTs match.
  // Old provider cleanup must never disconnect the replacement connection.
  const connectionToken = activeRoomConnection.token ?? data?.livekit?.token
  const connectionAttempt = activeRoomConnection.attempt
  const room = useMemo(() => {
    void connectionAttempt
    return new Room(roomOptions)
  }, [roomOptions, connectionAttempt])

  useEffect(() => {
    /**
     * Warm up connection to LiveKit server before joining room
     * This prefetch helps reduce initial connection latency by establishing
     * an early HTTP connection to the WebRTC signaling server
     *
     * It should cache DNS and TLS keys.
     */
    const prepareConnection = async () => {
      if (!apiConfig || isConnectionWarmedUp) return
      await room.prepareConnection(apiConfig.livekit.url)

      if (isFireFox() && apiConfig.livekit.enable_firefox_proxy_workaround) {
        try {
          const wssUrl =
            apiConfig.livekit.url
              .replace('https://', 'wss://')
              .replace(/\/$/, '') + '/rtc'

          /**
           * FIREFOX + PROXY WORKAROUND:
           *
           * Issue: On Firefox behind proxy configurations, WebSocket signaling fails to establish.
           * Symptom: Client receives HTTP 200 instead of expected 101 (Switching Protocols).
           * Root Cause: Certificate/security issue where the initial request is considered unsecure.
           *
           * Solution: Pre-establish a WebSocket connection to the signaling server, which fails.
           * This "primes" the connection, allowing subsequent WebSocket establishments to work correctly.
           *
           * Note: This issue is reproducible on LiveKit's demo app.
           * Reference: livekit-examples/meet/issues/466
           */
          const ws = new WebSocket(wssUrl)
          // 401 unauthorized response is expected
          ws.onerror = () => ws.readyState <= 1 && ws.close()
        } catch (e) {
          console.debug('Firefox WebSocket workaround failed.', e)
        }
      }

      setIsConnectionWarmedUp(true)
    }
    prepareConnection()
  }, [room, apiConfig, isConnectionWarmedUp])

  const isMobile = useIsMobile()

  const hasAutoMutedRef = useRef(false)

  const { recoverSession, stopRecovery } = useBreakoutRecovery(roomId)

  // LiveKit's connection effect depends on onError. Keep it stable while the
  // store changes during a swap, or the old token reconnects the room we left.
  const handleRoomError = useCallback(
    (error: Error) => {
      const failure = getMediaDeviceFailure(error)
      if (failure && failure !== MediaDeviceFailure.Other) return

      if (
        error instanceof ConnectionError &&
        error.reason === ConnectionErrorReason.Cancelled
      ) {
        void captureEvent('connection-cancelled')
        return
      }

      const wasTransitioning = breakoutStore.isTransitioning
      failBreakoutConnection(error)
      if (wasTransitioning && room.state !== 'connected') recoverSession()

      reportError('livekit_room_error', error, { path: 'connect_publish' })
    },
    [recoverSession, room]
  )

  /*
   * Ensure stable WebSocket connection URL. This is critical for legacy browser compatibility
   * (Firefox <124, Chrome <125, Edge <125) where HTTPS URLs in WebSocket() constructor
   *  may fail - the force_wss_protocol flag allows explicit WSS protocol conversion
   */
  const serverUrl = useMemo(() => {
    const livekit_url = apiConfig?.livekit.url
    if (!livekit_url) return
    if (apiConfig?.livekit.force_wss_protocol) {
      return livekit_url.replace('https://', 'wss://')
    }
    return livekit_url
  }, [apiConfig?.livekit])

  const { t } = useTranslation('rooms')
  if (isCreateError) {
    // this error screen should be replaced by a proper waiting room for anonymous user.
    return (
      <ErrorScreen
        title={t('error.createRoom.heading')}
        body={t('error.createRoom.body')}
      />
    )
  }

  // Some clients (like DINUM) operate in bandwidth-constrained environments
  // These settings help ensure successful connections in poor network conditions
  const connectOptions = {
    maxRetries: 5, // Default: 1. Only for unreachable server scenarios
    peerConnectionTimeout: 60000, // Default: 15s. Extended for slow TURN/TLS negotiation
  }

  return (
    <QueryAware status={isFetchError ? createStatus : fetchStatus}>
      <Screen header={false} footer={false}>
        <LiveKitRoom
          room={room}
          serverUrl={serverUrl}
          key={connectionAttempt}
          token={connectionToken}
          connect={isConnectionWarmedUp}
          audio={
            breakoutSnap.pendingMediaIntent ? false : userConfig.audioEnabled
          }
          video={
            !breakoutSnap.pendingMediaIntent &&
            userConfig.videoEnabled && {
              processor: BackgroundProcessorFactory.fromProcessorConfig(
                userConfig.processorConfig
              ),
            }
          }
          connectOptions={connectOptions}
          className={css({
            backgroundColor: 'primaryDark.50 !important',
          })}
          onError={handleRoomError}
          onConnected={async () => {
            const connectedRoomName = room.name
            breakoutStore.currentBreakoutRoomLkName =
              connectedRoomName && connectedRoomName !== data?.livekit?.room
                ? connectedRoomName
                : null
            breakoutStore.connectionLost = false
            stopRecovery()
            const pendingHelp = breakoutStore.pendingHelpAcknowledgement
            const acknowledgePendingHelp = async () => {
              if (
                !pendingHelp ||
                connectedRoomName !== pendingHelp.expectedLivekitRoomName
              ) {
                return
              }
              await acknowledgeConnectedHelp({
                pending: pendingHelp,
                connectedRoomName,
                acknowledge: (request) => acknowledgeBreakoutHelp(request),
                invalidate: (roomId, sessionId) =>
                  queryClient.invalidateQueries({
                    queryKey: breakoutHelpRequestsKey(roomId, sessionId),
                  }),
              })
              clearMatchingPendingHelpAcknowledgement(pendingHelp)
            }
            const mediaIntent = breakoutStore.pendingMediaIntent
            const restoredTransition = await finishBreakoutConnection({
              mediaIntent,
              setCameraEnabled: (enabled) =>
                room.localParticipant.setCameraEnabled(enabled),
              setMicrophoneEnabled: (enabled) =>
                room.localParticipant.setMicrophoneEnabled(enabled),
              onMediaRestoreError: (error) => {
                breakoutStore.transitionError =
                  error instanceof Error
                    ? error.message
                    : 'media_restore_failed'
              },
              completeTransition: completeBreakoutTransition,
              afterTransition: acknowledgePendingHelp,
            })
            if (restoredTransition) return
            if (!apiConfig) return
            if (
              userPreferencesSnap.is_auto_mute_large_room_enabled &&
              !hasAutoMutedRef.current &&
              userConfig.audioEnabled &&
              room.numParticipants > apiConfig.auto_mute_on_join_threshold
            ) {
              hasAutoMutedRef.current = true
              await room.localParticipant.setMicrophoneEnabled(false)
              notifyAutoMutedOnJoin()
            }
          }}
          onDisconnected={(e) => {
            const leaveMeeting = () => {
              clearBreakoutState()
              const metadata = { room_id: roomId }
              switch (e) {
                case DisconnectReason.CLIENT_INITIATED:
                  navigateTo('feedback', {}, { state: { ...metadata } })
                  return
                default:
                  // Everything else, INCLUDING a disconnect with no reason at
                  // all, must still land somewhere. Reconnect exhaustion and
                  // token-expiry joins arrive with no reason, and the switch
                  // previously matched nothing for them: the participant was
                  // left on a dead conference with no overlay and no exit.
                  navigateTo(
                    'feedback',
                    {},
                    { state: { reason: e, ...metadata } }
                  )
              }
            }

            const action = resolveDisconnectAction({
              reason: e,
              isTransitioning: breakoutStore.isTransitioning,
              activeSessionId: breakoutStore.activeSessionId,
              currentBreakoutRoomLkName:
                breakoutStore.currentBreakoutRoomLkName,
            })

            if (action === 'ignore') return
            if (action === 'recover-session') {
              recoverSession(e)
              return
            }
            if (action === 'verify-assignment') {
              const sessionId = breakoutStore.activeSessionId
              const previous = breakoutStore.currentBreakoutRoomLkName
              if (!sessionId || !data?.id) {
                leaveMeeting()
                return
              }
              void fetchCurrentBreakoutAssignment(data.id, sessionId)
                .then((fresh) => {
                  if (isRemovalAReassignment(previous, fresh)) recoverSession(e)
                  else leaveMeeting()
                })
                .catch(() => leaveMeeting())
              return
            }
            leaveMeeting()
          }}
        >
          <WatchMediaDeviceErrors />
          <BreakoutWatcher
            currentRoomSlug={roomId}
            setActiveRoomConnection={setActiveRoomConnection}
            mainRoomId={data?.id ?? ''}
          />
          {(breakoutSnap.isTransitioning || breakoutSnap.connectionLost) && (
            <BreakoutTransition />
          )}
          {/* BreakoutActions owns useBreakoutRoomSwap — must stay inside <LiveKitRoom> */}
          <BreakoutActions
            roomId={roomId}
            setActiveRoomConnection={setActiveRoomConnection}
            mainRoomId={data?.id ?? ''}
          />
          <VideoConference />
          {!isMobile && <InviteDialog mode={mode} />}
          <PictureInPictureConference />
          <MeetDevtools />
        </LiveKitRoom>
      </Screen>
    </QueryAware>
  )
}
