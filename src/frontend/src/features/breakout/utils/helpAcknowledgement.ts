export interface PendingHelpAcknowledgement {
  roomId: string
  sessionId: string
  helpRequestId: string
  expectedBreakoutRoomId: string
  expectedLivekitRoomName: string
  assignmentRevision: number
}

interface AcknowledgeConnectedHelpOptions {
  pending: Readonly<PendingHelpAcknowledgement> | null
  connectedRoomName?: string
  acknowledge: (request: {
    roomId: string
    sessionId: string
    helpRequestId: string
    expectedBreakoutRoomId: string
    expectedAssignmentRevision: number
  }) => Promise<unknown>
  invalidate: (roomId: string, sessionId: string) => Promise<unknown>
}

/** Acknowledge help only after reaching the exact room and revision target. */
export const acknowledgeConnectedHelp = async ({
  pending,
  connectedRoomName,
  acknowledge,
  invalidate,
}: AcknowledgeConnectedHelpOptions): Promise<boolean> => {
  if (!pending || connectedRoomName !== pending.expectedLivekitRoomName) {
    return false
  }

  try {
    await acknowledge({
      roomId: pending.roomId,
      sessionId: pending.sessionId,
      helpRequestId: pending.helpRequestId,
      expectedBreakoutRoomId: pending.expectedBreakoutRoomId,
      expectedAssignmentRevision: pending.assignmentRevision,
    })
    await invalidate(pending.roomId, pending.sessionId)
    return true
  } catch {
    // The durable server-side alert stays open after a stale or failed ack.
    return false
  }
}
