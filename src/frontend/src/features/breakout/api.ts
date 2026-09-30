import { fetchApi } from '@/api/fetchApi'
import { ApiError } from '@/api/ApiError'
import type { ApiLiveKit } from '@/features/rooms/api/ApiRoom'

export type BreakoutPerson = { identity: string; name: string }

export type BreakoutSession = {
  id: string
  status: 'active' | 'closed'
  rooms: { id: string; name: string; participants: BreakoutPerson[] }[]
}

export type BreakoutAssignment = {
  session_id: string
  room: { id: string; name: string }
}

export type CreateBreakoutSession = {
  rooms: { name: string; participants: BreakoutPerson[] }[]
}

const sessionsUrl = (roomId: string) => `/rooms/${roomId}/breakout-sessions/`

export const breakoutSessionKey = (roomId?: string) => [
  'breakoutSession',
  roomId,
]

export const fetchBreakoutSession = async (roomId: string) => {
  const sessions = await fetchApi<BreakoutSession[]>(sessionsUrl(roomId))
  return sessions[0] ?? null
}

export const createBreakoutSession = (
  roomId: string,
  body: CreateBreakoutSession
) =>
  fetchApi<BreakoutSession>(sessionsUrl(roomId), {
    method: 'POST',
    body: JSON.stringify(body),
  })

export const closeBreakoutSession = (roomId: string, sessionId: string) =>
  fetchApi(`${sessionsUrl(roomId)}${sessionId}/close/`, { method: 'POST' })

// Resolves to null when the caller has no room in the active session.
export const fetchBreakoutAssignment = (roomId: string) =>
  fetchApi<BreakoutAssignment>(
    `${sessionsUrl(roomId)}current-assignment/`
  ).catch((error) => {
    if (error instanceof ApiError && error.statusCode === 404) return null
    throw error
  })

export const joinBreakoutRoom = (
  roomId: string,
  sessionId: string,
  breakoutRoomId: string
) =>
  fetchApi<ApiLiveKit>(
    `${sessionsUrl(roomId)}${sessionId}/rooms/${breakoutRoomId}/join/`,
    { method: 'POST' }
  )
