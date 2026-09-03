"""Permission classes for the breakout rooms feature."""

from rest_framework import permissions

from .models import BreakoutAssignment


def get_participant_identity(user):
    """Extract the LiveKit identity from a user.

    Authenticated users use ``user.sub``; anonymous users must supply
    their stable ``participant_id`` via query/body parameter (handled
    by the viewset).
    """
    if user.is_anonymous:
        return None
    return str(user.sub)


class IsAssignedToBreakoutRoom(permissions.BasePermission):
    """Allow access only to participants assigned to the specific breakout room."""

    message = "You are not assigned to this breakout room."

    def has_object_permission(self, request, view, obj):
        """Check if the requesting user is assigned to this breakout room.

        ``obj`` is a ``BreakoutRoom`` instance.
        """
        identity = get_participant_identity(request.user)

        # Anonymous participants pass their identity via request data
        if identity is None:
            identity = request.data.get("participant_id") or request.query_params.get(
                "participant_id"
            )

        if not identity:
            return False

        return BreakoutAssignment.objects.filter(
            breakout_room=obj,
            participant_identity=identity,
        ).exists()


class CanManageBreakout(permissions.BasePermission):
    """Allow only room administrators/owners to manage breakout sessions.

    Requires the parent room to be resolved in the view via ``get_room()``.
    """

    message = (
        "You must be an administrator or owner of the room to manage breakout sessions."
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return True

    def has_object_permission(self, request, view, obj):
        """``obj`` is a BreakoutSession — check privileges on its parent room."""
        return obj.room.is_administrator_or_owner(request.user)
