# Local browser acceptance

Status: Verified locally

Run `bin/test-e2e-local` from the repository root. The suite must start its own
PostgreSQL, Redis, Django, Celery worker, Beat, and LiveKit services, build the
frontend, exercise real HTTP and WebRTC connections in Chromium, and remove its
containers and volumes even after a failure. It must leave HTML reports, traces,
and service logs in the local artifact directory.

Acceptance cases:

- A host and two anonymous participants join the same meeting. The host creates
  and assigns two breakout rooms through the UI. LiveKit must report each
  participant in exactly one expected room, not just a successful token request.
- Camera and microphone choices survive assignment, manual return, rejoin,
  reassignment, and recall. Enabled synthetic video must actually arrive at a
  remote browser; disabled tracks must remain disabled on the media server.
- Participants request and cancel help. A visiting host receives another room's
  help request, joins it, and acknowledges it. Announcements reach both rooms.
- Closing recalls participants, removes the media rooms, and permits a new
  session without inheriting the previous session's deliberate-return state.
- A failed join request is retried through the browser. Concurrent edits reject
  stale revisions and the host can retry against refreshed state.
- Waiting and unauthorised callers cannot read private announcements or enter
  another participant's breakout room. Accepted guests retain their own access.
- Repeated tokens still start a fresh connection attempt after a failure.
- An expired session is closed by the real Beat/worker path without a host browser.

The only substitutes are browser-generated camera/microphone input and seeded
Django login sessions. OIDC, recording/egress, external integrations, every
browser/platform, and manual assistive-technology acceptance are outside this
suite. Test configuration and seed code are outside the application package;
there are no test login endpoints or production authentication bypasses.
