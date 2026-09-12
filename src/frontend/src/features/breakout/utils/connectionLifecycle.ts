interface MediaIntent {
  camera: boolean
  microphone: boolean
}

interface FinishBreakoutConnectionOptions {
  mediaIntent: MediaIntent | null
  setCameraEnabled: (enabled: boolean) => Promise<unknown>
  setMicrophoneEnabled: (enabled: boolean) => Promise<unknown>
  onMediaRestoreError: (error: unknown) => void
  completeTransition: () => void
  afterTransition: () => Promise<void>
}

/** Restore independent media intent before running non-media post-connect work. */
export const finishBreakoutConnection = async ({
  mediaIntent,
  setCameraEnabled,
  setMicrophoneEnabled,
  onMediaRestoreError,
  completeTransition,
  afterTransition,
}: FinishBreakoutConnectionOptions): Promise<boolean> => {
  if (!mediaIntent) {
    await afterTransition()
    return false
  }

  const results = await Promise.allSettled([
    setCameraEnabled(mediaIntent.camera),
    setMicrophoneEnabled(mediaIntent.microphone),
  ])
  const failure = results.find(
    (result): result is PromiseRejectedResult => result.status === 'rejected'
  )
  if (failure) onMediaRestoreError(failure.reason)

  completeTransition()
  await afterTransition()
  return true
}
