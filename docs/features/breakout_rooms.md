# Breakout rooms

Status: Experimental and disabled by default

Breakout rooms let room owners and administrators divide an active meeting into
temporary LiveKit rooms, supervise those rooms, recall participants, and close
the breakout session. The feature remains behind `MEET_BREAKOUT_ROOMS_ENABLED`
until the automated and live acceptance checks described here have passed.

## Roles and access

- Only a room owner or administrator can create, configure, activate, supervise,
  broadcast to, or close a breakout session.
- Participants are identified from server state. Authenticated participants use
  their account subject; anonymous main-room LiveKit identities are derived from
  a signed, HttpOnly, room-scoped guest capability. A request body, display name,
  or visible LiveKit identity never proves a participant's identity.
- A participant may obtain a token only for their current assignment. A manager
  may visit any breakout room without becoming assigned to it.
- Ordinary participants can retrieve only their own assignment. The complete
  assignment map is available only to managers and is never stored in shared
  LiveKit room metadata.
- Management rights come from the LiveKit `room_role` attribute, kept during a
  visit through the moderator-visit flag. Guests are identified by the signed,
  room-scoped cookie on every token path, including direct entry to a public
  room. A breakout room name is never served as an unregistered room.

## Session and assignment state

A session progresses through configuring, activating, active, closing, and
closed states. Activating and closing are observable, retryable effect states:
the API must not report success before the required LiveKit operations complete.
An upstream failure remains visible on the session and can be retried safely.
Parent-room metadata updates share a lock across breakout, recording, and room
configuration writers so concurrent updates preserve unrelated metadata keys.

One participant has at most one assignment in a session, enforced by the
database. Assignment and current connection location are separate: visiting the
main room does not clear an assignment, and the participant can return to it.
Every assignment change increments a monotonic revision. Clients treat every
data packet as a hint and re-read the assignment endpoint; nothing acts on
packet content.

Reassignment disconnects the participant from the old breakout room, publishes
a server-originated revision hint, and issues short-lived join tokens bounded by
the session's absolute end time. LiveKit can refresh connected clients' tokens
beyond this initial lifetime; removing a participant on self-hosted LiveKit does
not revoke those credentials. The authenticated `participant_joined` webhook checks
every breakout admission against the current database assignment and removes a
stale connection. This is eventual containment, not synchronous admission
control, so its latency and failure behaviour are part of live acceptance.
See the [LiveKit token lifecycle](https://docs.livekit.io/frontends/reference/tokens-grants/).

The latest host announcement (`last_broadcast_message`, at most 500 characters)
is stored on the session, readable by every participant of that session
through the assignment poll, and cleared when the session closes. An unassigned
caller must have room access or an accepted lobby admission; a waiting or denied
guest capability proves identity but does not grant access to announcements.

## Room transitions and media

The client snapshots the tracks that are actually publishing immediately before
a room transition. It connects to the target with camera and microphone disabled,
then restores only the tracks that were publishing. Moving, returning, visiting,
reassigning, retrying, and being recalled must never enable a device the user had
disabled. Breakout tokens also preserve the main room's exact publication-source
policy, including an explicit empty list.

Transitions complete from LiveKit connection events rather than fixed delays.
Failures remain visible and offer a retry. Each connection token owns a fresh
LiveKit transport, including same-room reconnects, so old-provider cleanup cannot
disconnect the replacement. Joining a help room already connected is a no-op. When a returning guest's lobby admission has expired, the client
reloads into the lobby page with an explanation and keeps its deliberate-return
intent. Any other unplanned disconnect inside a breakout room shows a
reconnecting state, asks the assignment poll what to do, and leaves to the
feedback page after 15 s without an answer. After a successful connection, a later drop starts a fresh grace period. Failed
retries within one outage do not extend its deadline. A visiting manager recovers
to the main meeting. A disconnect that carries no
reason at all — reconnect exhaustion, token expiry — no longer falls through
silently in any position: outside a breakout room it ends on the feedback page
like any other.
Connection failures retain the captured media intent and pending close/recall
completion until a connection succeeds, except on the lobby re-entry path,
which starts over. A retry must not replace that intent with the muted tracks
of an incomplete connection or initial device preferences.

## Lifecycle and cleanup

An empty main room is valid while participants are in breakout rooms and does
not close the session. If LiveKit recreates the main room, its start webhook
restores session metadata under the same lock used by closing and reassignment.
Timed sessions use an absolute `ends_at` boundary.
Untimed sessions remain active until explicitly closed.

Cleanup is an idempotent Celery task scheduled by a separate Beat process. Its
schedule database uses writable storage: `/tmp` in Compose and an `emptyDir`
mounted at `/var/run/celery` in Helm.
LiveKit creation, authoritative metadata, participant removal, and room deletion
failures are reported as retryable upstream failures rather than being silently
converted into success. Advisory real-time hints are best effort because clients
recover from the API source of truth. Status failures are reported as unknown,
never as zero attendance. A missing main LiveKit room is treated as already
absent during close and cannot block breakout deletion or assignment
reconciliation.

An expired empty breakout room or a participant that has already disconnected
is already reconciled. Only an explicit LiveKit `not_found` response has this
meaning; authentication, transport, and other upstream failures remain retryable.
The admission webhook rejects joins after `ends_at`, even if scheduled cleanup
has not yet changed the session status.

The webhook scope filter applies to the parent meeting id; breakout rooms
unknown to this deployment are ignored. While a breakout session is open,
`room_finished` on the main room does not purge lobby admissions; entries
still expire on their own TTL (accepted: `LOBBY_ACCEPTED_TIMEOUT`, 6 h by
default), which bounds an untimed session's guest re-entry window. Sessions
are capped at 10 rooms; each server-originated hint costs two LiveKit API
calls per room plus one assignment poll per participant.

## Help requests

Help requests are durable records bound to the requester's server-derived
identity and current assignment. A participant has at most one open request per
session and may cancel it. Managers can list and acknowledge open requests from
the main room or any breakout room. Reassignment moves an open request to the
participant's current room and revision; removing the assignment cancels it.
Starting session closure cancels every open help request in the same transaction,
including when a later LiveKit operation fails. Cancellation and acknowledgement
are serialized with assignment changes so terminal help states cannot overwrite
one another.

Real-time messages contain only a server-originated invalidation event and
never serve as authorization or the source of help-request content.
Participant-originated control packets can only trigger a re-read of server
state, throttled to one every two seconds for help lists.

## Feature availability

`MEET_BREAKOUT_ROOMS_ENABLED` and `CELERY_ENABLED` (both must be true) gate only
the creation and activation of a session and the "create" entry point. Every
other endpoint (list, close, retry, status, assignments, join, broadcast, help
requests, current-assignment) keeps working for sessions that already exist,
and the panel stays reachable for their managers, so turning the flag off never
strands a live session. The scheduled cleanup task runs whenever a Celery Beat
process is up, regardless of the flag; it closes timed sessions and retries
failed effects. Operator rule: before turning the flag off, either wait until
`SELECT count(*) FROM meet_breakout_session WHERE status <> 'closed'` is 0, or
keep Beat running until it is (Helm: set `celeryBeat.enabled=true` in the same
upgrade, because `breakoutRooms.enabled=false` alone removes the Beat
deployment).

Attendance distinguishes actual LiveKit presence from assignment and exposes
upstream status failures as unknown or degraded.

## Acceptance command

The repository acceptance command is:

```bash
make test-breakout
```

It must run the backend breakout suite, frontend typecheck/tests/build, and task
registration checks. Deployment rendering and real-service integration remain
separate release gates. Any preflight-style guard added for this feature
must include a self-test mutation proving that the guard fails when its invariant
is deliberately broken.

## Release acceptance

Automated checks do not establish production readiness. Keep the production flag
disabled until the final candidate passes controlled multi-client browser tests,
reassignment and refreshed-token replay tests, webhook delay/outage tests, media
permission and reconnect tests, and keyboard/screen-reader acceptance. Record the
exact deployed commit, LiveKit version, worker/Beat configuration, and sanitized
evidence. Any unauthorized media or data exposure blocks release. Outstanding
review requests must be addressed before merge.
