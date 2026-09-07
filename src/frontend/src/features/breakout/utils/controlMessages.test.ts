import { describe, expect, it } from 'vitest'
import {
  classifyBreakoutHint,
  parseBreakoutControlMessage,
} from './controlMessages'

describe('breakout data packets are hints, never commands', () => {
  it('maps every breakout packet to a refresh of server state', () => {
    expect(classifyBreakoutHint({ type: 'breakout:revision' })).toBe('refresh')
    expect(classifyBreakoutHint({ type: 'breakout:help_revision' })).toBe(
      'help'
    )
    expect(classifyBreakoutHint({ type: 'breakout:recall' })).toBe('refresh')
    expect(classifyBreakoutHint({ type: 'breakout:close' })).toBe('refresh')
    expect(classifyBreakoutHint({ type: 'breakout:broadcast' })).toBe('refresh')
  })

  it('ignores packets that are not breakout packets', () => {
    expect(classifyBreakoutHint({ type: 'chat' })).toBeNull()
    expect(classifyBreakoutHint({})).toBeNull()
    expect(classifyBreakoutHint({ type: 42 })).toBeNull()
  })

  it('ignores malformed and non-object payloads safely', () => {
    const encode = (text: string) => new TextEncoder().encode(text)
    expect(parseBreakoutControlMessage(encode('{'))).toBeNull()
    expect(parseBreakoutControlMessage(encode('"text"'))).toBeNull()
  })
})
