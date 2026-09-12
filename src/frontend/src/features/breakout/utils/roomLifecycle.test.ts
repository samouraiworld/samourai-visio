import { describe, expect, it } from 'vitest'
import {
  DISCONNECTED,
  leaveCurrentRoom,
  swapRoomConnection,
} from './roomLifecycle'

const MAIN = 'main-meeting'
const BREAKOUT = 'breakout_s_0'

/** A deferred the test resolves by hand, to hold a disconnect open. */
const deferred = () => {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/**
 * livekit-client's `Room`, reduced to the two behaviours that decide whether a
 * breakout move lands:
 *
 *  - `connect()` returns immediately when already connected, logging
 *    `already connected to room <name>` and ignoring the token,
 *  - `disconnect()` only takes effect once its lock, leave and engine close
 *    have all resolved — here, once the test releases the gate.
 */
class FakeRoom {
  state = DISCONNECTED
  name: string | null = null
  log: string[] = []
  disconnectCalls = 0
  gate = deferred()

  constructor(joined?: string) {
    if (joined) {
      this.state = 'connected'
      this.name = joined
    }
    // Default to a disconnect that completes on its own.
    this.gate.resolve()
  }

  /** Hold the next disconnect open until the test releases it. */
  holdDisconnect() {
    this.gate = deferred()
    return this.gate
  }

  connect = async (token: string) => {
    if (this.state === 'connected') {
      this.log.push(`already connected to room ${this.name}`)
      return
    }
    this.state = 'connected'
    this.name = token
  }

  disconnect = async () => {
    // livekit-client's disconnect is idempotent: there is nothing to leave
    // when the engine is already closed.
    if (this.state === DISCONNECTED) return
    this.disconnectCalls += 1
    await this.gate.promise
    this.state = DISCONNECTED
    this.name = null
  }
}

/**
 * What `<LiveKitRoom>` does when its `key` changes: the unmount disconnects
 * fire-and-forget, then the new mount connects with the new token.
 */
const remountWithToken = (room: FakeRoom, token: string) => {
  void room.disconnect()
  return room.connect(token)
}

describe('leaveCurrentRoom', () => {
  it('is what carries a participant into the breakout room', async () => {
    const room = new FakeRoom(MAIN)
    room.holdDisconnect()

    const left = leaveCurrentRoom(room)
    // The disconnect is genuinely outstanding: nothing has moved yet.
    expect(room.state).toBe('connected')
    room.gate.resolve()
    await expect(left).resolves.toBe(true)

    await remountWithToken(room, BREAKOUT)

    expect(room.name).toBe(BREAKOUT)
    expect(room.log).toEqual([])
  })

  it('guards the defect: without it the token is dropped and nobody moves', async () => {
    const room = new FakeRoom(MAIN)
    room.holdDisconnect()

    // The remount on its own — the branch's behaviour before this module.
    await remountWithToken(room, BREAKOUT)

    expect(room.name).toBe(MAIN)
    expect(room.log).toEqual([`already connected to room ${MAIN}`])
  })

  it('reports that a participant outside a room had nothing to leave', async () => {
    const room = new FakeRoom()

    await expect(leaveCurrentRoom(room)).resolves.toBe(false)
    expect(room.disconnectCalls).toBe(0)
  })

  it('treats a missing room as nothing to leave', async () => {
    await expect(leaveCurrentRoom(null)).resolves.toBe(false)
    await expect(leaveCurrentRoom(undefined)).resolves.toBe(false)
  })

  it('surfaces a failed disconnect instead of reporting a move', async () => {
    const room = new FakeRoom(MAIN)
    const gate = room.holdDisconnect()
    const left = leaveCurrentRoom(room)
    gate.reject(new Error('leave_failed'))

    await expect(left).rejects.toThrow('leave_failed')
    // The participant is still in the meeting, for the caller to recover from.
    expect(room.state).toBe('connected')
    expect(room.name).toBe(MAIN)
  })
})

describe('swapRoomConnection', () => {
  it('does not publish the new token until the meeting has been left', async () => {
    const room = new FakeRoom(MAIN)
    const gate = room.holdDisconnect()
    const applied: string[] = []

    const swap = swapRoomConnection(room, BREAKOUT, (token) => {
      applied.push(token)
      void remountWithToken(room, token)
    })

    // The disconnect is outstanding, so nothing may have been published yet.
    expect(applied).toEqual([])

    gate.resolve()
    await swap

    expect(applied).toEqual([BREAKOUT])
    expect(room.name).toBe(BREAKOUT)
    expect(room.log).toEqual([])
  })

  it('publishes nothing when the meeting could not be left', async () => {
    const room = new FakeRoom(MAIN)
    const gate = room.holdDisconnect()
    const applied: string[] = []

    const swap = swapRoomConnection(room, BREAKOUT, (token) =>
      applied.push(token)
    )
    gate.reject(new Error('leave_failed'))

    await expect(swap).rejects.toThrow('leave_failed')
    expect(applied).toEqual([])
    expect(room.name).toBe(MAIN)
  })

  it('still publishes for a participant who was in no room', async () => {
    const room = new FakeRoom()
    const applied: string[] = []

    await swapRoomConnection(room, BREAKOUT, (token) => applied.push(token))

    expect(applied).toEqual([BREAKOUT])
  })
})
