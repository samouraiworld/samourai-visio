/**
 * Anonymous participant identity stabilization.
 *
 * Anonymous users get a random UUID as LiveKit identity at token time.
 * This module provides a stable identity persisted in sessionStorage,
 * so breakout room assignments survive page refreshes.
 */

import { STORAGE_KEYS } from './constants'

/**
 * Get a stable participant identity.
 *
 * - Authenticated users: returns their userId.
 * - Anonymous users: returns a sessionStorage-persisted UUID.
 */
export const getStableParticipantId = (
  isAnonymous: boolean,
  userId?: string
): string => {
  if (!isAnonymous && userId) return userId

  let anonId = sessionStorage.getItem(STORAGE_KEYS.ANON_PARTICIPANT_ID)
  if (!anonId) {
    anonId = crypto.randomUUID()
    sessionStorage.setItem(STORAGE_KEYS.ANON_PARTICIPANT_ID, anonId)
  }
  return anonId
}
