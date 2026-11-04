# Breakout rooms

A host can split a meeting into 2 to 10 smaller meetings, move everyone into the one they were assigned, and later bring everyone back.

## What a host does

1. In the meeting, the owner or an administrator opens the breakout panel, picks a number of rooms and assigns each participant to one of them, by hand or with a shuffle.
2. Open creates the rooms. Every assigned participant still in the meeting is moved to their room. Someone who joins the meeting later has no assignment and stays in it.
3. Close deletes the rooms, and everyone in them is sent back to the meeting they started in.

Only one split can be open in a meeting at a time. To change the assignments, close and open again.

## Enabling it

Set `MEET_BREAKOUT_ROOMS_ENABLED=True` on the backend. It is off by default. The frontend reads it from the config endpoint as `breakout_rooms.is_enabled`.

With the flag off, every breakout endpoint answers 404 except close, so a split opened before the flag was turned off can still be closed.

Nothing else is required: no worker, no scheduled task. The backend creates and deletes the rooms on LiveKit directly, and each call to LiveKit gives up after 5 seconds with a 503 the host can retry.

## What is stored

- A breakout session per split: the meeting, its state (`active` or `closed`), who opened it, and when it closed.
- A breakout room per smaller meeting: its display name and the name of its LiveKit room, `breakout_<session id>_<index>`.
- An assignment per participant: the room, the participant's identity in the meeting (the account's `sub` when signed in, the signed guest identity otherwise) and their display name at the time.

Closed sessions stay in the database. While a session is open, the main meeting's LiveKit metadata carries `{"breakout": {"session_id", "status"}}`, which tells the browsers in it to move.

## Limits

- A pass to a breakout room is valid for 60 seconds. LiveKit recreates a deleted room when someone joins it, so a pass fetched just before Close can reopen that room until it expires.
- Nobody can leave their breakout room and come back to it, and the host does not visit rooms.
- There is no timer: a split stays open until the host closes it.
