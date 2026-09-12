"""Settings available only inside the isolated browser test runtime."""

from typing import ClassVar

from meet.settings import Development


class E2E(Development):
    """Use real services and short cleanup polling without external integrations."""

    SESSION_ENGINE = "django.contrib.sessions.backends.db"
    MEET_BREAKOUT_ROOMS_ENABLED = True
    CELERY_ENABLED = True
    CELERY_TASK_ALWAYS_EAGER = False
    CELERY_BEAT_SCHEDULE: ClassVar[dict] = {
        "cleanup-stale-breakout-sessions": {
            "task": "core.breakout.tasks.cleanup_stale_breakout_sessions",
            "schedule": 2,
        },
    }
    STORAGES: ClassVar[dict] = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    RECORDING_ENABLE = False
    METADATA_COLLECTOR_ENABLED = False
