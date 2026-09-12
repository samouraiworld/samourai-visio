/**
 * A manager may open the breakout panel when the feature is enabled, or
 * when a session already exists: turning the flag off must never hide an
 * open session from the host who has to close it.
 */
export const canUseBreakoutRooms = (
  isEnabled: boolean | undefined,
  isAdminOrOwner: boolean,
  hasOpenSession = false
) => isAdminOrOwner && (isEnabled === true || hasOpenSession)
