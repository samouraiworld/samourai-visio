import { describe, expect, it } from 'vitest'
import { captureMediaIntent } from './mediaIntent'

describe('breakout media intent', () => {
  it('preserves disabled camera and microphone state', () => {
    expect(
      captureMediaIntent({
        isCameraEnabled: false,
        isMicrophoneEnabled: false,
      })
    ).toEqual({ camera: false, microphone: false })
  })

  it('preserves enabled camera and microphone state', () => {
    expect(
      captureMediaIntent({
        isCameraEnabled: true,
        isMicrophoneEnabled: true,
      })
    ).toEqual({ camera: true, microphone: true })
  })

  it('defaults missing publications to disabled', () => {
    expect(captureMediaIntent()).toEqual({
      camera: false,
      microphone: false,
    })
  })
})
