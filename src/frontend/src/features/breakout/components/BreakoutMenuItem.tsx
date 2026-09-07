/**
 * Menu item for "Breakout Rooms" in the Tools/Options menu.
 * Styled with variant: 'dark' for high-contrast visibility against the dark meeting UI.
 * Shown to managers when the feature is enabled or a session is already open.
 */

import { useTranslation } from 'react-i18next'
import { RiLayoutGridLine } from '@remixicon/react'
import { useSnapshot } from 'valtio'
import { layoutStore } from '@/stores/layout'
import { MenuItem } from 'react-aria-components'
import { menuRecipe } from '@/primitives/menuRecipe'
import { useConfig } from '@/api/useConfig'
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { useBreakoutSession } from '../api/useBreakoutSession'
import { breakoutStore } from '../stores/breakout'
import { canUseBreakoutRooms } from '../utils/featureGate'

export const BreakoutMenuItem = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout' })
  const room = useRoomData()
  const isAdminOrOwner = useIsAdminOrOwner()
  // A visiting host holds a member token inside a breakout room.
  const { isModeratorVisiting } = useSnapshot(breakoutStore)
  const canManage = isAdminOrOwner || isModeratorVisiting
  const { data: config } = useConfig()
  // Only managers poll: the list endpoint answers 403 to guests.
  const { data: session } = useBreakoutSession(canManage ? room?.id : undefined)

  if (
    !canUseBreakoutRooms(
      config?.breakout_rooms?.is_enabled,
      canManage,
      session !== null && session !== undefined
    )
  ) {
    return null
  }

  return (
    <MenuItem
      id="breakout-rooms"
      className={menuRecipe({ icon: true, variant: 'dark' }).item}
      onAction={() => {
        layoutStore.activePanelId = 'breakout' as never
        layoutStore.activeSubPanelId = null
      }}
    >
      <RiLayoutGridLine size={20} aria-hidden="true" />
      {t('menuItem')}
    </MenuItem>
  )
}
