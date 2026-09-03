"""Periodic tasks for breakout room cleanup."""

from logging import getLogger

from .services import BreakoutService

logger = getLogger(__name__)


def cleanup_stale_breakout_sessions():
    """Periodic task: auto-close breakout sessions that have exceeded
    their duration plus a grace period.

    Intended to be called via Celery beat, Django-Q, or a management command.
    """
    service = BreakoutService()
    closed_count = service.cleanup_stale_sessions()

    if closed_count:
        logger.info(
            "Cleaned up %d stale breakout session(s).",
            closed_count,
        )

    return closed_count
