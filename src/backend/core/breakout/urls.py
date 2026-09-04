"""URL configuration for the breakout rooms feature.

These URLs are nested under ``/api/v1.0/rooms/{room_id}/breakout-sessions/``.
"""

from django.urls import path

from . import viewsets

# ViewSet instance used by all endpoints
breakout_viewset = viewsets.BreakoutSessionViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    }
)

breakout_detail_viewset = viewsets.BreakoutSessionViewSet.as_view(
    {
        "patch": "partial_update",
    }
)

urlpatterns = [
    # Session CRUD
    path(
        "",
        breakout_viewset,
        name="breakout-session-list",
    ),
    path(
        "<uuid:pk>/",
        breakout_detail_viewset,
        name="breakout-session-detail",
    ),
    path(
        "<uuid:pk>/retry/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "retry"}),
        name="breakout-session-retry",
    ),
    # Live status
    path(
        "<uuid:pk>/status/",
        viewsets.BreakoutSessionViewSet.as_view({"get": "live_status"}),
        name="breakout-session-status",
    ),
    # Assignments
    path(
        "<uuid:pk>/assignments/",
        viewsets.BreakoutSessionViewSet.as_view({"put": "assignments"}),
        name="breakout-session-assignments",
    ),
    # Randomize
    path(
        "<uuid:pk>/randomize/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "randomize"}),
        name="breakout-session-randomize",
    ),
    # Broadcast announcement
    path(
        "<uuid:pk>/broadcast/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "broadcast"}),
        name="breakout-session-broadcast",
    ),
    # Request help beacon
    path(
        "<uuid:pk>/request-help/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "request_help"}),
        name="breakout-session-request-help",
    ),
    path(
        "<uuid:pk>/cancel-help/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "cancel_help"}),
        name="breakout-session-cancel-help",
    ),
    path(
        "<uuid:pk>/help-requests/",
        viewsets.BreakoutSessionViewSet.as_view({"get": "help_requests"}),
        name="breakout-session-help-requests",
    ),
    path(
        "<uuid:pk>/acknowledge-help/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "acknowledge_help"}),
        name="breakout-session-acknowledge-help",
    ),
    path(
        "<uuid:pk>/current-assignment/",
        viewsets.BreakoutSessionViewSet.as_view({"get": "current_assignment"}),
        name="breakout-session-current-assignment",
    ),
    # Join a specific breakout room
    path(
        "<uuid:pk>/rooms/<uuid:breakout_room_id>/join/",
        viewsets.BreakoutSessionViewSet.as_view({"post": "join_breakout_room"}),
        name="breakout-room-join",
    ),
]
