import {
  test,
  expect,
  seed,
  media,
  api,
  request,
  join,
  inRoom,
  namedIdentity,
  tracks,
  openPanel,
  createFromUI,
  closeFromUI,
  sessionPath,
  type Session,
} from './fixtures.js'

test('real participants move, retain media, request help, hear announcements, and restart', async ({
  actor,
}) => {
  const scenario = seed.lifecycle
  const host = await actor(scenario.owner)
  const alice = await actor()
  const bob = await actor()
  await join(host, scenario)
  await inRoom(scenario.owner.identity, scenario.roomId)
  await join(alice, scenario, 'Alice', true)
  await join(bob, scenario, 'Bob')
  const aliceId = await namedIdentity('Alice', scenario.roomId)
  const bobId = await namedIdentity('Bob', scenario.roomId)
  await tracks(aliceId, scenario.roomId, true)
  await tracks(bobId, scenario.roomId, false)
  // The host has no local camera, so a playing video proves remote media arrived.
  await expect
    .poll(() =>
      host
        .locator('video')
        .evaluateAll((videos) =>
          videos.some(
            (video) =>
              video instanceof HTMLVideoElement &&
              video.readyState >= 2 &&
              video.videoWidth > 0 &&
              video.currentTime > 0
          )
        )
    )
    .toBe(true)

  let session = await createFromUI(host, scenario)
  const [first, second] = session.breakout_rooms
  await host
    .getByRole('combobox', { name: 'Assign Alice to a room', exact: true })
    .selectOption(first.id)
  await expect(
    host.getByRole('button', { name: 'Unassign Alice', exact: true })
  ).toBeVisible()
  await host
    .getByRole('combobox', { name: 'Assign Bob to a room', exact: true })
    .selectOption(second.id)
  await expect(
    host.getByRole('button', { name: 'Unassign Bob', exact: true })
  ).toBeVisible()
  await host
    .getByRole('button', { name: 'Open All Rooms', exact: true })
    .click()
  await inRoom(aliceId, first.livekit_room_name)
  await inRoom(bobId, second.livekit_room_name)
  await tracks(aliceId, first.livekit_room_name, true)
  await tracks(bobId, second.livekit_room_name, false)

  await host
    .getByPlaceholder('Type announcement to all rooms...')
    .fill('Please compare your notes')
  await host
    .getByRole('button', { name: 'Send announcement', exact: true })
    .click()
  await expect(
    alice.getByText('Please compare your notes', { exact: true })
  ).toBeVisible()
  await expect(
    bob.getByText('Please compare your notes', { exact: true })
  ).toBeVisible()
  await alice.getByRole('button', { name: 'Ask for Help', exact: true }).click()
  await expect(
    alice.getByRole('button', { name: 'Cancel help request', exact: true })
  ).toBeVisible()
  await expect(
    host.getByRole('button', { name: 'Join Room', exact: true })
  ).toBeVisible()
  await alice
    .getByRole('button', { name: 'Cancel help request', exact: true })
    .click()
  await expect(
    host.getByRole('button', { name: 'Join Room', exact: true })
  ).toHaveCount(0)
  await expect(
    alice.getByRole('button', { name: 'Ask for Help', exact: true })
  ).toBeVisible()
  // Cancellation does not bypass the real per-participant help cooldown.
  await expect(async () => {
    if (
      await alice
        .getByRole('button', { name: 'Cancel help request', exact: true })
        .isVisible()
    )
      return
    await alice
      .getByRole('button', { name: 'Ask for Help', exact: true })
      .click()
    await expect(
      alice.getByRole('button', { name: 'Cancel help request', exact: true })
    ).toBeVisible({ timeout: 1000 })
  }).toPass({ timeout: 25_000, intervals: [2000, 4000, 5000] })
  await host.getByRole('button', { name: 'Join Room', exact: true }).click()
  await inRoom(scenario.owner.identity, first.livekit_room_name)
  await expect
    .poll(() =>
      host
        .locator('video')
        .evaluateAll((videos) =>
          videos.some(
            (video) =>
              video instanceof HTMLVideoElement &&
              video.readyState >= 2 &&
              video.videoWidth > 0 &&
              video.currentTime > 0
          )
        )
    )
    .toBe(true)
  await expect(
    alice.getByRole('button', { name: 'Ask for Help', exact: true })
  ).toBeVisible()
  await bob.getByRole('button', { name: 'Ask for Help', exact: true }).click()
  await host.getByRole('button', { name: 'Join Room', exact: true }).click()
  await inRoom(scenario.owner.identity, second.livekit_room_name)
  await expect(
    bob.getByRole('button', { name: 'Ask for Help', exact: true })
  ).toBeVisible()

  await alice
    .getByRole('button', { name: 'Return to main room', exact: true })
    .click()
  await inRoom(aliceId, scenario.roomId)
  await tracks(aliceId, scenario.roomId, true)
  await alice
    .getByRole('button', { name: 'Return to assigned room', exact: true })
    .click()
  await inRoom(aliceId, first.livekit_room_name)
  await tracks(aliceId, first.livekit_room_name, true)
  await openPanel(host)
  await host
    .getByRole('combobox', { name: 'Move Bob to another room', exact: true })
    .selectOption(first.id)
  await inRoom(bobId, first.livekit_room_name)
  await tracks(bobId, first.livekit_room_name, false)
  // Deliberately pause Alice in main before closing; the next session must move her again.
  await alice
    .getByRole('button', { name: 'Return to main room', exact: true })
    .click()
  await inRoom(aliceId, scenario.roomId)
  await closeFromUI(host, scenario)
  await inRoom(aliceId, scenario.roomId)
  await inRoom(bobId, scenario.roomId)
  await inRoom(scenario.owner.identity, scenario.roomId)
  await tracks(aliceId, scenario.roomId, true)
  await tracks(bobId, scenario.roomId, false)
  await expect
    .poll(async () =>
      (await media.listRooms()).filter((room) =>
        session.breakout_rooms.some(
          (breakout) => breakout.livekit_room_name === room.name
        )
      )
    )
    .toEqual([])

  session = await createFromUI(host, scenario)
  await host
    .getByRole('combobox', { name: 'Assign Alice to a room', exact: true })
    .selectOption(session.breakout_rooms[0].id)
  await expect(
    host.getByRole('button', { name: 'Unassign Alice', exact: true })
  ).toBeVisible()
  await host
    .getByRole('button', { name: 'Open All Rooms', exact: true })
    .click()
  await inRoom(aliceId, session.breakout_rooms[0].livekit_room_name)
  await closeFromUI(host, scenario)
  await inRoom(aliceId, scenario.roomId)
})

test('a failed assignment join retries and stale manager changes are rejected', async ({
  actor,
}) => {
  const scenario = seed.retry
  const host = await actor(scenario.owner)
  const guest = await actor()
  let injectConnectionFailure = false
  let failedConnections = 0
  // Install before navigation so the socket interceptor exists in the document.
  await guest.routeWebSocket(/\/rtc(?:\/|\?|$)/, (socket) => {
    if (injectConnectionFailure && failedConnections++ === 0)
      socket.close({ code: 1011, reason: 'Injected connection failure' })
    else socket.connectToServer()
  })
  await join(host, scenario)
  await join(guest, scenario, 'Retry guest')
  const identity = await namedIdentity('Retry guest', scenario.roomId)
  const session = await createFromUI(host, scenario)
  let joinFailures = 0
  await guest.route('**/breakout-sessions/*/rooms/*/join/', async (route) => {
    if (joinFailures++ === 0) await route.abort('connectionfailed')
    else await route.continue()
  })
  injectConnectionFailure = true
  let concurrentEdit = false
  await host.route('**/breakout-sessions/*/assignments/', async (route) => {
    if (!concurrentEdit) {
      concurrentEdit = true
      const original = route.request().postDataJSON()
      // A second manager wins the revision immediately before this browser's write.
      await api(host, `${sessionPath(scenario, session)}assignments/`, 'PUT', {
        revision: original.revision,
        assignments: {
          [session.breakout_rooms[1].id]: [{ identity, name: 'Retry guest' }],
        },
      })
    }
    await route.continue()
  })
  const selector = host.getByRole('combobox', {
    name: 'Assign Retry guest to a room',
    exact: true,
  })
  await selector.selectOption(session.breakout_rooms[0].id)
  await expect(
    host
      .getByRole('alert')
      .filter({ hasText: 'The rooms changed in the meantime.' })
  ).toBeVisible()
  await expect(selector).toHaveValue(session.breakout_rooms[1].id)
  await selector.selectOption(session.breakout_rooms[0].id)
  await expect(selector).toHaveValue(session.breakout_rooms[0].id)
  await expect(
    host
      .getByRole('alert')
      .filter({ hasText: 'The rooms changed in the meantime.' })
  ).toHaveCount(0)
  await host
    .getByRole('button', { name: 'Open All Rooms', exact: true })
    .click()
  await inRoom(identity, session.breakout_rooms[0].livekit_room_name)
  expect(joinFailures).toBeGreaterThanOrEqual(2)
  expect(failedConnections).toBeGreaterThanOrEqual(2)
  await tracks(identity, session.breakout_rooms[0].livekit_room_name, false)
  await closeFromUI(host, scenario)
  await inRoom(identity, scenario.roomId)
})

test('private announcements and assignments require actual admission', async ({
  actor,
}) => {
  const scenario = seed.private
  const host = await actor(scenario.owner)
  const waiting = await actor()
  const outsider = await actor(seed.outsider)
  await join(host, scenario)
  const session = await api<Session>(host, sessionPath(scenario), 'POST', {
    num_rooms: 2,
    duration_seconds: null,
  })
  await api(host, sessionPath(scenario, session), 'PATCH', {
    status: 'active',
  })
  await api(host, `${sessionPath(scenario, session)}broadcast/`, 'POST', {
    message: 'Private discussion',
  })
  await api(waiting, `/rooms/${scenario.roomId}/request-entry/`, 'POST', {
    username: 'Waiting guest',
  })
  for (const page of [waiting, outsider]) {
    const response = await request(
      page,
      `${sessionPath(scenario, session)}current-assignment/`
    )
    expect(response.status()).toBe(403)
    expect(await response.text()).not.toContain('Private discussion')
  }
  await api(outsider, `/rooms/${scenario.roomId}/request-entry/`, 'POST', {
    username: 'Signed-in waiting guest',
  })
  expect(
    (
      await request(
        outsider,
        `${sessionPath(scenario, session)}current-assignment/`
      )
    ).status()
  ).toBe(403)
  const roster = await api<{
    participants: { id: string; username: string }[]
  }>(host, `/rooms/${scenario.roomId}/waiting-participants/`)
  const participant = roster.participants.find(
    (p) => p.username === 'Waiting guest'
  )!
  expect(participant).toBeDefined()
  await api(host, `/rooms/${scenario.roomId}/enter/`, 'POST', {
    participant_id: participant.id,
    allow_entry: true,
  })
  const accepted = await request(
    waiting,
    `${sessionPath(scenario, session)}current-assignment/`
  )
  expect(accepted.status()).toBe(200)
  expect(await accepted.text()).toContain('Private discussion')
  const signedInParticipant = roster.participants.find(
    (p) => p.username === 'Signed-in waiting guest'
  )!
  expect(signedInParticipant).toBeDefined()
  await api(host, `/rooms/${scenario.roomId}/enter/`, 'POST', {
    participant_id: signedInParticipant.id,
    allow_entry: true,
  })
  const signedInAccepted = await request(
    outsider,
    `${sessionPath(scenario, session)}current-assignment/`
  )
  expect(signedInAccepted.status()).toBe(200)
  expect(await signedInAccepted.text()).toContain('Private discussion')
  const unauthorizedJoin = await request(
    waiting,
    `${sessionPath(scenario, session)}rooms/${session.breakout_rooms[0].id}/join/`,
    'POST',
    {}
  )
  expect(unauthorizedJoin.status()).toBe(403)
  await api(host, sessionPath(scenario, session), 'PATCH', {
    status: 'closed',
  })
})

test('Beat and worker expire a session after the host leaves', async ({
  actor,
}) => {
  test.setTimeout(150_000)
  const scenario = seed.timer
  const host = await actor(scenario.owner)
  await join(host, scenario)
  await inRoom(scenario.owner.identity, scenario.roomId)
  const session = await api<Session>(host, sessionPath(scenario), 'POST', {
    num_rooms: 2,
    duration_seconds: 60,
  })
  const active = await api<Session>(
    host,
    sessionPath(scenario, session),
    'PATCH',
    { status: 'active' }
  )
  expect(active.ends_at).not.toBeNull()
  // No mounted breakout watcher can close this session: its only browser leaves.
  await host.goto('about:blank')
  expect((await api<Session[]>(host, sessionPath(scenario)))[0].status).toBe(
    'active'
  )
  let firstClosedAt: number | undefined
  await expect
    .poll(
      async () => {
        const sessions = await api<Session[]>(host, sessionPath(scenario))
        if (!sessions.length) firstClosedAt ??= Date.now()
        return sessions
      },
      { timeout: 110_000, intervals: [1000] }
    )
    .toEqual([])
  expect(firstClosedAt!).toBeGreaterThanOrEqual(
    Date.parse(active.ends_at!) - 1000
  )
  const rooms = (await media.listRooms()).map((room) => room.name)
  for (const room of session.breakout_rooms)
    expect(rooms).not.toContain(room.livekit_room_name)
})
