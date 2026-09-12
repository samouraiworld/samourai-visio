interface ParticipantMediaState {
  isCameraEnabled?: boolean
  isMicrophoneEnabled?: boolean
}

export const captureMediaIntent = (
  participant?: ParticipantMediaState
): { camera: boolean; microphone: boolean } => ({
  camera: participant?.isCameraEnabled ?? false,
  microphone: participant?.isMicrophoneEnabled ?? false,
})
