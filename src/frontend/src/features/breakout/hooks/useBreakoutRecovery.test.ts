// @vitest-environment jsdom
import { act, cleanup, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { breakoutStore, clearBreakoutState } from '../stores/breakout'
import { useBreakoutRecovery } from './useBreakoutRecovery'

const navigate = vi.hoisted(() => vi.fn())
vi.mock('@/navigation/navigateTo', () => ({ navigateTo: navigate }))
beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  clearBreakoutState()
})
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

it('bounds repeated failed connection attempts by one recovery deadline', () => {
  const { result } = renderHook(() => useBreakoutRecovery('main'))
  act(() => result.current.recoverSession())
  expect(breakoutStore.connectionLost).toBe(true)
  act(() => {
    vi.advanceTimersByTime(10000)
    result.current.recoverSession()
    vi.advanceTimersByTime(5000)
  })
  expect(navigate).toHaveBeenCalledWith(
    'feedback',
    {},
    { state: { reason: undefined, room_id: 'main' } }
  )
})

it('cancels recovery after a successful connection and allows a full new grace period', () => {
  const { result } = renderHook(() => useBreakoutRecovery('main'))
  act(() => {
    result.current.recoverSession()
    vi.advanceTimersByTime(10000)
    result.current.stopRecovery()
    breakoutStore.connectionLost = false
    vi.advanceTimersByTime(10000)
  })
  expect(navigate).not.toHaveBeenCalled()
  act(() => {
    result.current.recoverSession()
    vi.advanceTimersByTime(14999)
  })
  expect(navigate).not.toHaveBeenCalled()
  act(() => vi.advanceTimersByTime(1))
  expect(navigate).toHaveBeenCalledTimes(1)
})
