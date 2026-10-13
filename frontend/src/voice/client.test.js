// The real voice client with the browser's mic, audio and WebSocket faked.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../data/auth.js', () => ({ idToken: async () => 'dev:shree-auto:m-raju:mechanic' }))
vi.mock('../config.js', () => ({ wsBase: () => 'ws://test' }))

const { createVoice } = await import('./client.js')

let sockets, tracks, contexts, node

class FakeSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  constructor(url) {
    this.url = url
    this.sent = []
    this.readyState = FakeSocket.CONNECTING
    sockets.push(this)
  }
  send(data) { this.sent.push(data) }
  close() { this.readyState = FakeSocket.CLOSED }
  open() { this.readyState = FakeSocket.OPEN; this.onopen?.() }
}

class FakeAudioContext {
  constructor(opts = {}) {
    this.sampleRate = opts.sampleRate || 16000
    this.currentTime = 0
    this.closed = false
    this.destination = {}
    this.audioWorklet = { addModule: async () => {} }
    contexts.push(this)
  }
  createMediaStreamSource() { return { connect: () => {} } }
  createBuffer(_ch, length, rate) { return { duration: length / rate, copyToChannel: () => {} } }
  createBufferSource() { return { connect: () => {}, start: () => {}, stop: () => {} } }
  async close() { this.closed = true }
}

class FakeWorkletNode {
  constructor() { this.port = {}; node = this }
}

beforeEach(() => {
  sockets = []
  contexts = []
  tracks = [{ stopped: false, stop() { this.stopped = true } }]
  vi.stubGlobal('WebSocket', FakeSocket)
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('AudioWorkletNode', FakeWorkletNode)
  vi.stubGlobal('navigator', { mediaDevices: { getUserMedia: async () => ({ getTracks: () => tracks }) } })
})
afterEach(() => vi.unstubAllGlobals())

const frame = () => ({ data: new Float32Array(640).fill(0.2) }) // 40 ms at 16 kHz

describe('voice client', () => {
  it('opens one socket even when connect is called twice', async () => {
    const v = createVoice({ onEvent: () => {} })
    await Promise.all([v.connect(), v.connect()])
    await v.connect()
    expect(sockets).toHaveLength(1)
  })

  it('close stops the mic, the audio and the socket, and stays closed', async () => {
    const events = []
    const v = createVoice({ onEvent: (e) => events.push(e) })
    await v.connect()
    sockets[0].open()
    v.close()
    expect(tracks[0].stopped).toBe(true)
    expect(contexts.every((c) => c.closed)).toBe(true)
    expect(sockets[0].readyState).toBe(FakeSocket.CLOSED)
    await v.connect()
    expect(sockets).toHaveLength(1)
    node.port.onmessage?.(frame())
    expect(sockets[0].sent).toHaveLength(0)
  })

  it('hands-free: does not send the mic while the agent is speaking (no echo back to Gemini)', async () => {
    const v = createVoice({ onEvent: () => {}, handsFree: true })
    await v.connect()
    sockets[0].open()
    node.port.onmessage(frame())
    expect(sockets[0].sent).toHaveLength(1)
    sockets[0].onmessage({ data: new Int16Array(24000).buffer }) // one second of agent audio
    node.port.onmessage(frame())
    expect(sockets[0].sent).toHaveLength(1)
    contexts.forEach((c) => { c.currentTime = 5 }) // the agent has finished
    node.port.onmessage(frame())
    expect(sockets[0].sent).toHaveLength(2)
  })

  it('a connection replaced by another screen reports it and frees the mic', async () => {
    const events = []
    const v = createVoice({ onEvent: (e) => events.push(e) })
    await v.connect()
    sockets[0].open()
    sockets[0].onclose({ code: 4409 })
    expect(events.at(-1)).toMatchObject({ type: 'status', status: 'error', message: 'Opened on another screen.' })
    expect(tracks[0].stopped).toBe(true)
  })
})

describe('push-to-talk', () => {
  it('sends the whole turn including the last partial frame, then stop; a no-speech turn becomes a note', async () => {
    const events = []
    const v = createVoice({ onEvent: (e) => events.push(e), handsFree: false })
    await v.connect()
    sockets[0].open()
    node.port.onmessage({ data: new Float32Array(100) }) // not talking yet: nothing sent
    expect(sockets[0].sent).toHaveLength(0)
    v.startTalking()
    node.port.onmessage({ data: new Float32Array(400) }) // under 40 ms: held back until more comes
    expect(sockets[0].sent).toHaveLength(1)
    v.stopTalking()
    const sent = sockets[0].sent
    expect(JSON.parse(sent[0])).toEqual({ type: 'start' })
    expect(sent[1].byteLength).toBe(800) // flushed on release, not lost
    expect(JSON.parse(sent[2])).toEqual({ type: 'stop' })

    sockets[0].onmessage({ data: JSON.stringify({ type: 'ignored', reason: 'no speech' }) })
    expect(events.at(-2)).toEqual({ type: 'thinking', on: false })
    expect(events.at(-1)).toEqual({ type: 'note', text: "Didn't catch that. Hold the button and speak." })
  })
})
