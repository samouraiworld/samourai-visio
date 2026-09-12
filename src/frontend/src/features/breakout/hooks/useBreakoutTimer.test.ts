import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToString } from 'react-dom/server'
import { useBreakoutTimer } from './useBreakoutTimer'

// Effects never run during server rendering, so this is exactly the value the
// first browser render sees before any tick.
describe('useBreakoutTimer first render', () => {
  it('is not expired for a timed session that still has time', () => {
    const Probe = () => {
      const snapshot = useBreakoutTimer({
        status: 'active',
        started_at: new Date(Date.now() - 30_000).toISOString(),
        ends_at: new Date(Date.now() + 570_000).toISOString(),
      })
      // Plain text: renderToString escapes quotes, so no JSON here.
      return createElement(
        'i',
        null,
        `expired=${snapshot.isExpired};remaining=${snapshot.remaining}`
      )
    }
    const html = renderToString(createElement(Probe))
    expect(html).toContain('expired=false')
    expect(html).toMatch(/remaining=(569|570)/)
  })
})
