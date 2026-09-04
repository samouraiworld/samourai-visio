"""Periodic tasks for breakout room cleanup."""

from logging import getLogger

from core.tasks._task import task

from .services import BreakoutService

logger = getLogger(__name__)


@task
def cleanup_stale_breakout_sessions():
    """Close timed sessions at their deadline and retry failed close effects."""
    service = BreakoutService()
    reconciled_count = service.cleanup_stale_sessions()

    if reconciled_count:
        logger.info(
            "Reconciled %d stale breakout session(s).",
            reconciled_count,
        )

    return reconciled_count
