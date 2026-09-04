/**
 * Constants for the breakout rooms feature.
 */

/** Default values. */
export const BREAKOUT_DEFAULTS = {
  MIN_ROOMS: 2,
  MAX_ROOMS: 10,
  DEFAULT_ROOMS: 3,
  MIN_DURATION: 60,
  MAX_DURATION: 7200,
  DEFAULT_DURATION: 600,
  RECALL_WARNING_SECONDS: 60,
  STATUS_POLL_INTERVAL_MS: 5000,
} as const

/** sessionStorage keys for breakout state persistence. */
export const STORAGE_KEYS = {
  BREAKOUT_STATE: 'meet_breakout_state',
} as const
