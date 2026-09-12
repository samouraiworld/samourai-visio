export interface BreakoutControlMessage {
  type?: unknown
  [key: string]: unknown
}

export type BreakoutHint = 'help' | 'refresh'

/**
 * Any participant can publish a data packet, and the sender is undefined
 * whenever the publisher is missing from the local participant map, so no
 * packet is ever trusted for its content. It only tells us which server
 * state to re-read.
 */
export const classifyBreakoutHint = (
  data: BreakoutControlMessage
): BreakoutHint | null => {
  switch (data.type) {
    case 'breakout:help_revision':
      return 'help'
    case 'breakout:revision':
    case 'breakout:recall':
    case 'breakout:close':
    case 'breakout:broadcast':
      return 'refresh'
    default:
      return null
  }
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
