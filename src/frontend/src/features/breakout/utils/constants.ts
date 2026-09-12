/**
 * Constants for the breakout rooms feature.
 */

/** Default values. */
export const BREAKOUT_DEFAULTS = {
  MIN_ROOMS: 2,
  MAX_ROOMS: 10,
  DEFAULT_ROOMS: 3,
  DEFAULT_DURATION: 600,
  RECALL_WARNING_SECONDS: 60,
  STATUS_POLL_INTERVAL_MS: 5000,
  RECOVERY_TIMEOUT_MS: 15000,
} as const

/** sessionStorage keys for breakout state persistence. */
export const STORAGE_KEYS = {
  BREAKOUT_STATE: 'meet_breakout_state',
  BREAKOUT_REENTRY: 'meet_breakout_reentry',
} as const
