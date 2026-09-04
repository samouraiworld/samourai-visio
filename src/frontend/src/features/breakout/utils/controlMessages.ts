export interface BreakoutControlMessage {
  type?: unknown
  [key: string]: unknown
}

/** Only the LiveKit server may author breakout control messages. */
export const isTrustedBreakoutControlMessage = (
  data: BreakoutControlMessage,
  hasRemoteParticipant: boolean
): boolean => {
  const type = typeof data.type === 'string' ? data.type : ''
  return !(hasRemoteParticipant && type.startsWith('breakout:'))
}

export const parseBreakoutControlMessage = (
  payload: Uint8Array
): BreakoutControlMessage | null => {
  try {
    const parsed: unknown = JSON.parse(new TextDecoder().decode(payload))
    return parsed !== null && typeof parsed === 'object'
      ? (parsed as BreakoutControlMessage)
      : null
  } catch {
    return null
  }
}
