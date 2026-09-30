import { describe, expect, it } from 'vitest'
import {
  DISCONNECTED,
  leaveCurrentRoom,
  swapRoomConnection,
} from './roomLifecycle'

const MAIN = 'main-meeting'
const BREAKOUT = 'breakout_s_0'

const deferred = () => {
  let resolve!: () => void
  let reject!: (error: Error) => void
  const promise = new Promise<void>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

// livekit-client's Room reduced to what decides a move: connect() ignores the
// token when already connected, and disconnect() lands once the gate opens.
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
    this.gate.resolve()
  }

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
    if (this.state === DISCONNECTED) return
    this.disconnectCalls += 1
    await this.gate.promise
    this.state = DISCONNECTED
    this.name = null
  }
}

// What <LiveKitRoom> does on a key change: disconnect fire-and-forget, then connect.
const remountWithToken = (room: FakeRoom, token: string) => {
  void room.disconnect()
  return room.connect(token)
}

describe('leaveCurrentRoom', () => {
  it('waits for the disconnect, so the next connect uses the new token', async () => {
    const room = new FakeRoom(MAIN)
    room.holdDisconnect()

    const left = leaveCurrentRoom(room)
    expect(room.state).toBe('connected')
    room.gate.resolve()
    await expect(left).resolves.toBe(true)

    await remountWithToken(room, BREAKOUT)

    expect(room.name).toBe(BREAKOUT)
    expect(room.log).toEqual([])
  })

  it('reports that a participant outside a room had nothing to leave', async () => {
    const room = new FakeRoom()

    await expect(leaveCurrentRoom(room)).resolves.toBe(false)
    await expect(leaveCurrentRoom(null)).resolves.toBe(false)
    expect(room.disconnectCalls).toBe(0)
  })

  it('surfaces a failed disconnect instead of reporting a move', async () => {
    const room = new FakeRoom(MAIN)
    const gate = room.holdDisconnect()
    const left = leaveCurrentRoom(room)
    gate.reject(new Error('leave_failed'))

    await expect(left).rejects.toThrow('leave_failed')
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
