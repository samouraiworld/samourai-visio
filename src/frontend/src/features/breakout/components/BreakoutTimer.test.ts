import { describe, expect, it } from 'vitest'
import { findCrossedTimerMilestone } from '../utils/timerMilestones'

describe('breakout timer announcements', () => {
  it('does not announce ordinary one-second ticks', () => {
    expect(findCrossedTimerMilestone(44, 43)).toBeUndefined()
  })

  it('announces meaningful countdown thresholds', () => {
    expect(findCrossedTimerMilestone(61, 60)).toBe(60)
    expect(findCrossedTimerMilestone(11, 10)).toBe(10)
    expect(findCrossedTimerMilestone(1, 0)).toBe(0)
  })

  it('announces the most urgent threshold after a throttled timer jump', () => {
    expect(findCrossedTimerMilestone(90, 25)).toBe(30)
  })
})
