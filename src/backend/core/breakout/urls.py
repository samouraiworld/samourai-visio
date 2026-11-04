"""Breakout session routes, included under rooms/<room_id>/breakout-sessions/."""

from django.urls import path

from .viewsets import BreakoutSessionViewSet

urlpatterns = [
    path(
        "",
        BreakoutSessionViewSet.as_view({"get": "list", "post": "create"}),
        name="breakout-sessions",
    ),
    path(
        "current-assignment/",
        BreakoutSessionViewSet.as_view({"get": "current_assignment"}),
        name="breakout-sessions-current-assignment",
    ),
    path(
        "<uuid:pk>/close/",
        BreakoutSessionViewSet.as_view({"post": "close"}),
        name="breakout-sessions-close",
    ),
    path(
        "<uuid:pk>/rooms/<uuid:room_pk>/join/",
        BreakoutSessionViewSet.as_view({"post": "join"}),
        name="breakout-sessions-join",
    ),
]
