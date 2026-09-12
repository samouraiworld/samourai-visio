import { useTranslation } from 'react-i18next'
import { css } from '@/styled-system/css'
import type { ActionFailure } from '../utils/actionFailure'

export const BreakoutActionFailure = ({
  failure,
}: {
  failure: ActionFailure | null
}) => {
  const { t } = useTranslation('rooms', { keyPrefix: 'breakout.active' })
  if (!failure) return null
  return (
    <div
      role="alert"
      className={css({
        padding: 0.75,
        borderRadius: '8',
        backgroundColor: 'danger.subtle',
        color: 'danger.subtle-text',
        fontSize: 14,
      })}
    >
      {t(`actionFailed.${failure}`)}
    </div>
  )
}
