"""Celery registration tests for breakout room maintenance."""

import sys
from importlib import reload
from unittest import mock

from django.test import override_settings

from core.tasks import cleanup_stale_breakout_sessions

from meet.celery_app import app as celery_app

breakout_tasks = sys.modules["core.breakout.tasks"]


@mock.patch("core.breakout.tasks.BreakoutService")
def test_cleanup_task_is_discoverable_by_the_worker(mock_service):
    """The core task discovery package exports the scheduled task."""
    mock_service.return_value.cleanup_stale_sessions.return_value = 2

    assert cleanup_stale_breakout_sessions() == 2
    mock_service.return_value.cleanup_stale_sessions.assert_called_once_with()


def test_cleanup_task_is_registered_when_celery_is_enabled():
    """Beat's named task resolves in the worker registry used by deployments."""
    with override_settings(CELERY_ENABLED=True):
        task_module = reload(breakout_tasks)

    task_name = "core.breakout.tasks.cleanup_stale_breakout_sessions"
    assert task_module.cleanup_stale_breakout_sessions.name == task_name
    registered_task = celery_app.tasks[task_name]
    assert registered_task.name == task_name
    assert registered_task.run.__module__ == "core.breakout.tasks"
