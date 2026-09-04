/**
 * Menu item for "Breakout Rooms" in the Tools/Options menu.
 * Styled with variant: 'dark' for high-contrast visibility against the dark meeting UI.
 * Only shown to moderators when the feature flag is active.
 */

import { useTranslation } from 'react-i18next'
import { RiLayoutGridLine } from '@remixicon/react'
import { layoutStore } from '@/stores/layout'
import { MenuItem } from 'react-aria-components'
import { menuRecipe } from '@/primitives/menuRecipe'
import { useConfig } from '@/api/useConfig'
import { useRoomData } from '@/features/rooms/livekit/hooks/useRoomData'
import { canUseBreakoutRooms } from '../utils/featureGate'

export const BreakoutMenuItem = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout' })
  const room = useRoomData()
  const { data: config } = useConfig()

  if (
    !canUseBreakoutRooms(
      config?.breakout_rooms?.is_enabled,
      room?.is_administrable ?? false
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
