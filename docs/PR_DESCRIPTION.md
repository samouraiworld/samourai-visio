# feat(breakout): Breakout Rooms Sovereign Implementation

<div align="center">
  <img src="https://raw.githubusercontent.com/samouraiworld/samourai-visio/feat/breakout-rooms/docs/assets/breakout_rooms_demo.gif" width="850" alt="Breakout Rooms Full Lifecycle Demo" />
  <p><em>🎬 Complete 10-Scene Live Lifecycle: Setup, 1-Click Randomize, Active Supervision, SOS Beacon, Broadcast & Recall</em></p>
</div>

## Description

This PR introduces comprehensive **Breakout Rooms** support for Samouraï Visio, providing full feature parity with commercial standards (Zoom, Google Meet, MS Teams) while adhering to sovereign open-source standards (French DSFR design system, WebRTC/LiveKit scalability, WCAG AA accessibility).

Breakout rooms allow meeting hosts and moderators to split participants into smaller sub-groups for workshops, interactive trainings, and focused discussions, with real-time supervisory oversight, multi-room broadcasting, and seamless participant recall.

---

## 📸 Key UI Milestones & Screenshots

<details open>
<summary><b>🔎 Click to preview individual high-resolution UI states</b></summary>
<br/>

| 1. Distribution & 1-Click Randomize | 2. Active Supervisory Panel |
| :---: | :---: |
| <img src="https://raw.githubusercontent.com/samouraiworld/samourai-visio/feat/breakout-rooms/docs/assets/screenshots/04_participants_distributed.png" width="400" /> | <img src="https://raw.githubusercontent.com/samouraiworld/samourai-visio/feat/breakout-rooms/docs/assets/screenshots/05_rooms_opened_active_supervision.png" width="400" /> |
| *Automated participant balancing with unassigned tray* | *Real-time attendance, broadcast announcements, close all CTA* |

| 3. Participant Floating Overlay | 4. Host Supervisory Room Visit |
| :---: | :---: |
| <img src="https://raw.githubusercontent.com/samouraiworld/samourai-visio/feat/breakout-rooms/docs/assets/screenshots/05b_participant_overlay_alice.png" width="400" /> | <img src="https://raw.githubusercontent.com/samouraiworld/samourai-visio/feat/breakout-rooms/docs/assets/screenshots/08_host_visiting_room1.png" width="400" /> |
| *Synchronized timer, "Ask for Help", Return to main room* | *Host seamlessly visits Room 1 with Bob, leave anytime* |

</details>

---

## 🎬 Live Verification & UI Highlights

* **Host Setup & Distribution**: Configurable room counts (2 to 10), flexible durations (2m up to 4h, or untimed), 1-click automatic randomization, and manual per-participant assignment.
* **In-Meeting Supervision**: Dedicated supervisory panel showing attendance across all rooms, Main Room presence, and 1-click "Visit" / "Leave" actions.
* **In-Flight Live Reassignment**: Move participants dynamically between rooms mid-meeting with zero interruption.
* **Multi-Room Broadcast**: Instant text announcements delivered simultaneously across all breakout rooms via WebRTC DataChannels.
* **"Ask for Help" SOS Beacon**: One-click participant help request alerting the host with a high-priority banner and direct "Join Room" shortcut.
* **Automatic Recall & Timer Warning**: Synchronized countdown timers across all rooms with an automatic 60-second warning banner before closure.

---

## 🛡️ Multi-Perspective Audit & Hardening (Completed)

This implementation has undergone a comprehensive 4-perspective deep audit and hardening program:

### 1. Code Quality & Cybersecurity
- **ACID Database Boundaries**: All multi-step write operations (`create_session`, `assign_participants`) are wrapped in `transaction.atomic()`, preventing orphaned or partially assigned states on network or LiveKit blips.
- **Duration-Scoped Token TTL**: LiveKit breakout tokens enforce strict expiration matching `session.duration_seconds + 300s` grace period, preventing participants from lingering after sessions conclude.
- **Help Beacon Rate Limiting**: Added a cache-based 15-second cooldown per participant (`HTTP 429 Too Many Requests`), protecting WebSocket gateways and host notification panels from spam/DoS.
- **N+1 Query Elimination**: Pre-fetched `breakout_rooms__assignments` across all session management endpoints.
- **Strict RBAC**: Only room administrators and owners can manage breakout sessions. Regular members cannot create or manipulate rooms.

### 2. UX/UI & Accessibility (WCAG AA & French DSFR)
- **Room Stepper A11y**: Added `aria-pressed={n === numRooms}` and explicit `aria-label` on room selector buttons for screen readers.
- **Duration Selector**: Enhanced with Panda CSS focus ring (`0 0 0 2px rgba(0, 0, 145, 0.2)`).
- **Empty-State Tray Badge**: When all participants are assigned, displays a DSFR success green badge (*"All participants assigned" / "Tous les participants sont assignés"*).
- **Design Tokens**: Standardized on Panda CSS `primary` DSFR tokens instead of hardcoded hex values.
- **High-Contrast Overlay**: White text and icons (`#FFFFFF`) on dark video backgrounds ensuring crisp WCAG AA compliance.

### 3. Resilience & State Management
- **In-Component Room Swapping (`<LiveKitRoom key={roomName}>`)**: Swaps rooms directly in the React tree without full-page reloads, preserving device permissions.
- **Ephemeral LiveKit Rooms**: Auto-expiring LiveKit rooms with 30-minute `empty_timeout` — zero database clutter.
- **Refresh Resilience**: Tab-scoped identity persistence (`sessionStorage`) ensures participants rejoin their assigned breakout room seamlessly upon page refresh.

---

## 🧪 Testing & Verification Matrix

- **Backend Automated Tests**: **37 / 37 passing** (`pytest core/breakout/` in 3.34s — 100% pass rate).
- **Code Linter**: `ruff check core/breakout/` passes with **0 errors, 0 warnings**.
- **Frontend Production Build**: `panda codegen && tsc -b && vite build` built cleanly in 30.6s with **0 TypeScript errors**.
- **Multi-Participant Live Dogfooding**: Verified with 3 concurrent live WebRTC participants (Host, Alice, Bob) testing real-time assignment, LiveKit room transfers, broadcast alerts, and clean resets.

---

## 📁 Changes by Component

### Backend (`src/backend/core/breakout/`)
- `models.py`: `BreakoutSession`, `BreakoutRoom`, `BreakoutAssignment` with database uniqueness constraints.
- `services.py`: `BreakoutService` handling session lifecycle, LiveKit room creation, participant distribution, scoped token generation, and broadcasts.
- `viewsets.py`: REST API endpoints with ACID boundaries, rate limiting, and prefetch optimizations.
- `permissions.py`: Host privilege separation & room access control.
- `tasks.py`: Periodic Celery cleanup for stale sessions.
- `migrations/0023_...py`: Database schema migration.
- `tests/`: 37 comprehensive unit, integration, and chaos resilience tests.

### Frontend (`src/frontend/src/features/breakout/`)
- `components/`: `BreakoutPanel`, `BreakoutSetup`, `BreakoutActiveView`, `BreakoutTimer`, `BreakoutRecallBanner`, `BreakoutBroadcastBanner`, `BreakoutHelpAlertBanner`, `BreakoutParticipantOverlay`, `BreakoutMenuItem`.
- `stores/`: Valtio reactive state store (`breakoutStore`).
- `hooks/`: `useBreakoutRoomSwap`, `useBreakoutMetadataWatcher`, `useBreakoutTimer`, `useBreakoutIdentity`.
- `locales/`: 100% bilingual French and English key parity in `en/rooms.json` and `fr/rooms.json`.

---

## 🚀 How to Test Locally

1. Start the stack:
   ```bash
   docker compose up -d
   ```
2. Navigate to `http://localhost:3000/any-room-slug` in your browser.
3. Open the **More Options** (3-dots) menu and click **Breakout Rooms**.
4. Configure 2-4 rooms, select a duration, and click **Create Breakout Rooms**.
5. Test random/manual assignment, open the rooms, send a broadcast, and test closing all rooms.
6. Run automated test suite:
   ```bash
   docker compose exec app-dev pytest core/breakout/
   ```
