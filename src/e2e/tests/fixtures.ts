import { readFileSync } from 'node:fs'
import {
  test as base,
  expect,
  type BrowserContext,
  type Page,
} from '@playwright/test'
import { RoomServiceClient, TrackSource, ServerError } from 'livekit-server-sdk'

export { expect, TrackSource }
export type Session = {
  id: string
  revision: number
  status: string
  ends_at: string | null
  breakout_rooms: { id: string; name: string; livekit_room_name: string }[]
}
type Login = { identity: string; cookie: string }
export type Scenario = { roomId: string; slug: string; owner: Login }
export const seed = JSON.parse(
  readFileSync(process.env.E2E_SEED_PATH ?? '/artifacts/seed.json', 'utf8')
) as Record<'lifecycle' | 'retry' | 'private' | 'timer', Scenario> & {
  outsider: Login
}
export const media = new RoomServiceClient(
  'http://livekit:7880',
  'devkey-padded-for-minimum-len!-livekit',
  'secret-key-padded-for-minimum-len!-livekit'
)
const csrf = 'abcdefghijklmnopqrstuvwxyzABCDEF'
export const test = base.extend<{ actor: (login?: Login) => Promise<Page> }>({
  actor: async ({ browser }, use, testInfo) => {
    const contexts: BrowserContext[] = []
    const errors: string[] = []
    await use(async (login) => {
      const context = await browser.newContext({
        baseURL: 'http://localhost:3000',
        locale: 'en-GB',
        viewport: { width: 1440, height: 1000 },
        permissions: ['camera', 'microphone'],
      })
      context.setDefaultTimeout(30_000)
      contexts.push(context)
      await context.addCookies([
        { name: 'csrftoken', value: csrf, url: 'http://localhost:3000' },
        ...(login
          ? [
              {
                name: 'meet_sessionid',
                value: login.cookie,
                url: 'http://localhost:3000',
              },
            ]
          : []),
      ])
      const page = await context.newPage()
      page.on('pageerror', (error) => errors.push(error.message))
      return page
    })
    await testInfo.attach('browser-errors', {
      body: JSON.stringify(errors, null, 2),
      contentType: 'application/json',
    })
    await Promise.all(contexts.map((context) => context.close()))
    expect(errors, 'No uncaught browser exceptions').toEqual([])
  },
})

export const sessionPath = (scenario: Scenario, session?: Session) =>
  `/rooms/${scenario.roomId}/breakout-sessions/${session ? `${session.id}/` : ''}`

export async function request(
  page: Page,
  path: string,
  method = 'GET',
  data?: unknown
) {
  const cookies = await page.context().cookies()
  return page.request.fetch(`/api/v1.0${path}`, {
    method,
    data,
    headers: {
      'X-CSRFToken': cookies.find((c) => c.name === 'csrftoken')?.value ?? csrf,
    },
  })
}
export async function api<T = unknown>(
  page: Page,
  path: string,
  method = 'GET',
  data?: unknown
): Promise<T> {
  const response = await request(page, path, method, data)
  expect(
    response.ok(),
    `${method} ${path}: ${response.status()} ${await response.text()}`
  ).toBeTruthy()
  return response.status() === 204 ? (undefined as T) : response.json()
}
export async function currentSession(
  page: Page,
  scenario: Scenario
): Promise<Session> {
  const sessions = await api<Session[]>(page, sessionPath(scenario))
  expect(sessions).toHaveLength(1)
  return sessions[0]
}
export async function presence(identity: string) {
  const rooms = await media.listRooms()
  const rosters = await Promise.all(
    rooms.map(async (room) => ({
      room: room.name,
      participants: await media
        .listParticipants(room.name)
        .catch((error: unknown) => {
          // Cleanup may delete a room between listing rooms and reading its roster.
          if (error instanceof ServerError && error.code === 'not_found')
            return []
          throw error
        }),
    }))
  )
  return rosters
    .filter((room) => room.participants.some((p) => p.identity === identity))
    .map((r) => r.room)
    .sort()
}
export async function inRoom(identity: string, name: string) {
  await expect
    .poll(() => presence(identity), {
      message: `${identity} connected only to ${name}`,
    })
    .toEqual([name])
}
export async function namedIdentity(name: string, room: string) {
  await expect
    .poll(async () =>
      (await media.listParticipants(room)).some((p) => p.name === name)
    )
    .toBe(true)
  return (await media.listParticipants(room)).find((p) => p.name === name)!
    .identity
}
export async function tracks(identity: string, room: string, enabled: boolean) {
  await expect
    .poll(
      async () => {
        const participant = (await media.listParticipants(room)).find(
          (p) => p.identity === identity
        )
        if (!participant) return null
        return [TrackSource.CAMERA, TrackSource.MICROPHONE].map((source) =>
          participant.tracks.some(
            (track) => track.source === source && !track.muted
          )
        )
      },
      { message: `${identity} camera/microphone enabled=${enabled}` }
    )
    .toEqual([enabled, enabled])
}
export async function join(
  page: Page,
  scenario: Scenario,
  name?: string,
  enabled = false
) {
  await page.goto(`/${scenario.slug}?silentLogin=false`)
  if (name)
    await page.getByRole('textbox', { name: /^Your name(?: |$)/ }).fill(name)
  for (const device of ['camera', 'microphone']) {
    const desired = page.getByRole('button', {
      name: new RegExp(`^${enabled ? 'Disable' : 'Enable'} ${device}(?: |$)`),
    })
    const opposite = page.getByRole('button', {
      name: new RegExp(`^${enabled ? 'Enable' : 'Disable'} ${device}(?: |$)`),
    })
    await expect(desired.or(opposite)).toBeVisible()
    if (await opposite.isVisible()) await opposite.click()
    await expect(desired).toBeVisible()
  }
  await page.getByRole('button', { name: 'Join', exact: true }).click()
  if (name) await namedIdentity(name, scenario.roomId)
  else await inRoom(scenario.owner.identity, scenario.roomId)
}
export async function openPanel(page: Page) {
  if (
    await page
      .getByRole('button', { name: 'Hide breakout rooms (Escape)' })
      .isVisible()
  )
    return
  await page.getByRole('button', { name: 'More Options', exact: true }).click()
  await page
    .getByRole('menuitem', { name: 'Breakout Rooms', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Hide breakout rooms (Escape)' })
  ).toBeVisible()
}
export async function createFromUI(page: Page, scenario: Scenario) {
  await openPanel(page)
  await page.getByRole('button', { name: '2 rooms', exact: true }).click()
  await page
    .getByRole('combobox', { name: 'Duration', exact: true })
    .selectOption('0')
  await page
    .getByRole('button', { name: 'Create Breakout Rooms', exact: true })
    .click()
  await expect(
    page.getByRole('button', { name: 'Open All Rooms', exact: true })
  ).toBeVisible()
  return currentSession(page, scenario)
}
export async function closeFromUI(page: Page, scenario: Scenario) {
  await openPanel(page)
  await page
    .getByRole('button', { name: 'Close All Rooms', exact: true })
    .click()
  await expect.poll(async () => api(page, sessionPath(scenario))).toEqual([])
}
