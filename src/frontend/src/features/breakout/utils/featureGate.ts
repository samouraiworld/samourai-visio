export const canUseBreakoutRooms = (
  isEnabled: boolean | undefined,
  isAdminOrOwner: boolean
) => isEnabled === true && isAdminOrOwner
