"""UUID-constrained breakout endpoints nested under the parent meeting."""

from django.urls import path

from rest_framework.routers import SimpleRouter

from .viewsets import BreakoutSessionViewSet

router = SimpleRouter(use_regex_path=False)
router.register("", BreakoutSessionViewSet, basename="breakout-session")

# Keep the established reverse name for callers of the nested join endpoint.
urlpatterns = [
    path(
        "<uuid:pk>/rooms/<uuid:breakout_room_id>/join/",
        BreakoutSessionViewSet.as_view({"post": "join_breakout_room"}),
        name="breakout-room-join",
    ),
    *router.urls,
]
