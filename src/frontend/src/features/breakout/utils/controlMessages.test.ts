import { describe, expect, it } from 'vitest'
import {
  isTrustedBreakoutControlMessage,
  parseBreakoutControlMessage,
} from './controlMessages'

describe('breakout control message trust boundary', () => {
  it.each([
    'breakout:recall',
    'breakout:close',
    'breakout:broadcast',
    'breakout:revision',
    'breakout:help_revision',
  ])('rejects participant-authored %s packets', (type) => {
    expect(isTrustedBreakoutControlMessage({ type }, true)).toBe(false)
  })

  it('accepts server-authored breakout packets', () => {
    expect(
      isTrustedBreakoutControlMessage({ type: 'breakout:recall' }, false)
    ).toBe(true)
  })

  it('ignores malformed and non-object payloads safely', () => {
    expect(
      parseBreakoutControlMessage(new TextEncoder().encode('{'))
    ).toBeNull()
    expect(
      parseBreakoutControlMessage(new TextEncoder().encode('"text"'))
    ).toBeNull()
  })
})
