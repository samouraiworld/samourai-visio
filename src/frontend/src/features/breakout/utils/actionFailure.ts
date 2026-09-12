import { ApiError } from '@/api/ApiError'

export type ActionFailure =
  | 'conflict'
  | 'upstream'
  | 'forbidden'
  | 'gone'
  | 'generic'

/** Map a refused manager action to the message the host needs. */
export const classifyActionFailure = (error: unknown): ActionFailure => {
  if (!(error instanceof ApiError)) return 'generic'
  switch (error.statusCode) {
    case 409:
      return 'conflict'
    case 503:
      return 'upstream'
    case 403:
      return 'forbidden'
    case 404:
      return 'gone'
    default:
      return 'generic'
  }
}
