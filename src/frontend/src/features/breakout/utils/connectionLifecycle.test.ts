import { describe, expect, it, vi } from 'vitest'
import { finishBreakoutConnection } from './connectionLifecycle'

describe('finishBreakoutConnection', () => {
  it('restores the microphone even when camera restoration fails', async () => {
    const setCameraEnabled = vi
      .fn<(enabled: boolean) => Promise<void>>()
      .mockRejectedValue(new Error('camera unavailable'))
    const setMicrophoneEnabled = vi
      .fn<(enabled: boolean) => Promise<void>>()
      .mockResolvedValue(undefined)
    const onMediaRestoreError = vi.fn()
    const completeTransition = vi.fn()

    await finishBreakoutConnection({
      mediaIntent: { camera: true, microphone: true },
      setCameraEnabled,
      setMicrophoneEnabled,
      onMediaRestoreError,
      completeTransition,
      afterTransition: async () => undefined,
    })

    expect(setCameraEnabled).toHaveBeenCalledWith(true)
    expect(setMicrophoneEnabled).toHaveBeenCalledWith(true)
    expect(onMediaRestoreError).toHaveBeenCalledOnce()
    expect(completeTransition).toHaveBeenCalledOnce()
  })

  it('completes media restoration before a pending acknowledgement settles', async () => {
    let releaseAcknowledgement: (() => void) | undefined
    const acknowledgement = new Promise<void>((resolve) => {
      releaseAcknowledgement = resolve
    })
    const completeTransition = vi.fn()
    const afterTransition = vi.fn(() => acknowledgement)

    const completion = finishBreakoutConnection({
      mediaIntent: { camera: false, microphone: true },
      setCameraEnabled: async () => undefined,
      setMicrophoneEnabled: async () => undefined,
      onMediaRestoreError: vi.fn(),
      completeTransition,
      afterTransition,
    })

    await vi.waitFor(() => {
      expect(afterTransition).toHaveBeenCalledOnce()
    })
    expect(completeTransition).toHaveBeenCalledOnce()

    releaseAcknowledgement?.()
    await completion
  })
})
