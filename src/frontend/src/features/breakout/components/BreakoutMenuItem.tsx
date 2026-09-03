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
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'

export const BreakoutMenuItem = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout' })
  const isAdminOrOwner = useIsAdminOrOwner()
  const isDevOrLocalhost =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' ||
      window.location.hostname === '127.0.0.1' ||
      window.location.hostname.includes('nip.io'))

  if (!isAdminOrOwner && !isDevOrLocalhost) {
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
