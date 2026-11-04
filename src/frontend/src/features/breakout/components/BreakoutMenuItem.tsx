import { RiLayoutGridLine } from '@remixicon/react'
import { MenuItem } from 'react-aria-components'
import { useTranslation } from 'react-i18next'
import { useRoomInfo } from '@livekit/components-react'
import { menuRecipe } from '@/primitives/menuRecipe'
import { useConfig } from '@/api/useConfig'
import { useSidePanel } from '@/features/rooms/livekit/hooks/useSidePanel'
import { useIsAdminOrOwner } from '@/features/rooms/livekit/hooks/useIsAdminOrOwner'
import { readBreakoutSessionId } from '../utils/transitions'

export const BreakoutMenuItem = () => {
  const { t } = useTranslation('rooms', { keyPrefix: 'options.items' })
  const { toggleBreakout } = useSidePanel()
  const isAdminOrOwner = useIsAdminOrOwner()
  const { data: config } = useConfig()
  const { metadata } = useRoomInfo()

  // Closed while the config loads; an open session stays closable with the flag off.
  const isEnabled = config?.breakout_rooms?.is_enabled === true
  if (!isAdminOrOwner || !(isEnabled || readBreakoutSessionId(metadata)))
    return null

  return (
    <MenuItem
      onAction={() => toggleBreakout()}
      className={menuRecipe({ icon: true, variant: 'dark' }).item}
    >
      <RiLayoutGridLine size={20} />
      {t('breakout')}
    </MenuItem>
  )
}
