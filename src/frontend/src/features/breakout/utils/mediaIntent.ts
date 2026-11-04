export type MediaIntent = { camera: boolean; microphone: boolean }

interface ParticipantMediaState {
  isCameraEnabled?: boolean
  isMicrophoneEnabled?: boolean
}

export const captureMediaIntent = (
  participant?: ParticipantMediaState
): MediaIntent => ({
  camera: participant?.isCameraEnabled ?? false,
  microphone: participant?.isMicrophoneEnabled ?? false,
})
