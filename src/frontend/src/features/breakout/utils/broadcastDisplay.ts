/** An announcement older than this at first sight is history, not news. */
export const BROADCAST_FRESHNESS_MS = 10_000

/**
 * Show each announcement exactly once: a late joiner, a refresh or a re-opened
 * session must not replay the last message as if it were new.
 */
export const shouldShowBroadcast = (
  lastShownAt: string | null,
  sentAt: string,
  now: number
): boolean => {
  if (lastShownAt !== null && Date.parse(lastShownAt) >= Date.parse(sentAt)) {
    return false
  }
  return now - Date.parse(sentAt) <= BROADCAST_FRESHNESS_MS
}
