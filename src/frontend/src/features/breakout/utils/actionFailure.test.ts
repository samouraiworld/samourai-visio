import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/ApiError'
import { classifyActionFailure } from './actionFailure'

describe('classifyActionFailure', () => {
  it('maps the statuses the breakout API returns', () => {
    expect(classifyActionFailure(new ApiError(409, {}))).toBe('conflict')
    expect(classifyActionFailure(new ApiError(503, {}))).toBe('upstream')
    expect(classifyActionFailure(new ApiError(403, {}))).toBe('forbidden')
    expect(classifyActionFailure(new ApiError(404, {}))).toBe('gone')
    expect(classifyActionFailure(new ApiError(400, {}))).toBe('generic')
  })

  it('treats anything else as generic', () => {
    expect(classifyActionFailure(new Error('network'))).toBe('generic')
    expect(classifyActionFailure(undefined)).toBe('generic')
  })
})
