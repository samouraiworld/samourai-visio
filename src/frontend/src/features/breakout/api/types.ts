/**
 * TypeScript types for the breakout rooms feature.
 */

export interface BreakoutAssignment {
  id: string
  participant_identity: string
  participant_name: string
}

export interface BreakoutRoom {
  id: string
  name: string
  livekit_room_name: string
  order: number
  assignments: BreakoutAssignment[]
}

export interface BreakoutSession {
  id: string
  status: 'configuring' | 'active' | 'closed'
  duration_seconds: number | null
  started_at: string | null
  closed_at: string | null
  created_at: string
  breakout_rooms: BreakoutRoom[]
}

export interface BreakoutRoomStatus {
  id: string
  name: string
  livekit_room_name: string
  order: number
  participant_count: number
  participants: { identity: string; name: string }[]
}

export interface BreakoutSessionStatus {
  session_id: string
  status: string
  started_at: string | null
  duration_seconds: number | null
  rooms: BreakoutRoomStatus[]
}

export interface BreakoutLiveKitConnection {
  livekit: {
    url: string
    room: string
    token: string
  }
}

/** Structure embedded in LiveKit room metadata for breakout state. */
export interface BreakoutMetadata {
  session_id: string
  status: 'active' | 'closed'
  started_at?: string
  duration_seconds?: number | null
  assignments: Record<
    string,
    {
      breakout_room_id: string
      breakout_room_name: string
      livekit_room_name: string
    }
  >
  rooms: {
    id: string
    name: string
    livekit_room_name: string
    order: number
  }[]
}
