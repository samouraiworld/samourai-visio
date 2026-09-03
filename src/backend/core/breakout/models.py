"""Models for the breakout rooms feature.

Breakout rooms are ephemeral sub-conference rooms within a meeting.
They exist only as LiveKit rooms — no Django Room records are created.
State is tracked in these lightweight models; actual media routing is
handled entirely by LiveKit.
"""

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _

from core.models import BaseModel


class BreakoutSession(BaseModel):
    """An ephemeral breakout session tied to a parent Room.

    Only one session can be active (configuring or active) per room at
    a time, enforced by the ``one_active_session_per_room`` constraint.
    """

    class Status(models.TextChoices):
        """Status choices for breakout session."""

        CONFIGURING = "configuring", _("Configuring")
        ACTIVE = "active", _("Active")
        CLOSED = "closed", _("Closed")

    room = models.ForeignKey(
        "core.Room",
        on_delete=models.CASCADE,
        related_name="breakout_sessions",
        verbose_name=_("parent room"),
        help_text=_("The main meeting room this breakout session belongs to."),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CONFIGURING,
        verbose_name=_("session status"),
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_breakout_sessions",
        verbose_name=_("created by"),
    )
    duration_seconds = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name=_("duration in seconds"),
        help_text=_(
            "Optional timer duration. Participants are recalled when it expires."
        ),
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("started at"),
        help_text=_("Timestamp when the session was activated."),
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("closed at"),
        help_text=_("Timestamp when the session was closed."),
    )

    class Meta:
        app_label = "core"
        db_table = "meet_breakout_session"
        ordering = ("-created_at",)
        verbose_name = _("Breakout Session")
        verbose_name_plural = _("Breakout Sessions")
        constraints = [
            models.UniqueConstraint(
                fields=["room"],
                condition=models.Q(status__in=["configuring", "active"]),
                name="one_active_session_per_room",
            ),
        ]

    def __str__(self):
        return f"BreakoutSession({self.room_id}, {self.status})"

    @property
    def is_active(self):
        """Return True if session is active."""
        return self.status == self.Status.ACTIVE

    @property
    def is_configuring(self):
        """Return True if session is configuring."""
        return self.status == self.Status.CONFIGURING

    @property
    def is_closed(self):
        """Return True if session is closed."""
        return self.status == self.Status.CLOSED


class BreakoutRoom(BaseModel):
    """One ephemeral sub-room within a breakout session.

    This model stores metadata only — the actual media room is a LiveKit
    room identified by ``livekit_room_name``.  No corresponding Django
    ``Room`` record is created.
    """

    session = models.ForeignKey(
        BreakoutSession,
        on_delete=models.CASCADE,
        related_name="breakout_rooms",
        verbose_name=_("breakout session"),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("display name"),
        help_text=_('User-visible room name, e.g. "Room 1".'),
    )
    livekit_room_name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name=_("LiveKit room name"),
        help_text=_(
            "The identifier used for the LiveKit room (prefixed with 'breakout_')."
        ),
    )
    order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("display order"),
    )

    class Meta:
        app_label = "core"
        db_table = "meet_breakout_room"
        ordering = ("order", "created_at")
        verbose_name = _("Breakout Room")
        verbose_name_plural = _("Breakout Rooms")

    def __str__(self):
        return f"{self.name} ({self.livekit_room_name})"

    @staticmethod
    def generate_livekit_room_name(session_id, index):
        """Generate a namespaced LiveKit room name.

        Format: ``breakout_{session_uuid}_{index}``
        This ensures no collision with main room UUIDs and makes breakout
        rooms instantly identifiable in logs and LiveKit admin.
        """
        return f"breakout_{session_id}_{index}"


class BreakoutAssignment(BaseModel):
    """Junction model: one participant → one breakout room per session.

    Uses ``participant_identity`` (the LiveKit identity, i.e. ``user.sub``
    for authenticated users or a stable session-scoped UUID for anonymous
    participants) as the link.

    Uniqueness within a session is enforced at the service layer and via
    a partial unique index when the DB supports it.
    """

    breakout_room = models.ForeignKey(
        BreakoutRoom,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name=_("breakout room"),
    )
    participant_identity = models.CharField(
        max_length=255,
        verbose_name=_("participant identity"),
        help_text=_("LiveKit identity (user.sub or stable anonymous UUID)."),
    )
    participant_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name=_("participant display name"),
        help_text=_("Display name at the time of assignment."),
    )

    class Meta:
        app_label = "core"
        db_table = "meet_breakout_assignment"
        ordering = ("created_at",)
        verbose_name = _("Breakout Assignment")
        verbose_name_plural = _("Breakout Assignments")

    def __str__(self):
        return f"{self.participant_name or self.participant_identity} → {self.breakout_room.name}"
