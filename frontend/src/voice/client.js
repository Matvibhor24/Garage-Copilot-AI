// Real voice client: phone mic -> /ws/voice -> Gemini Live (through the backend), agent audio back.
// Emits the same events as the demo voice (src/demo/voice.js):
//   status {status: connecting|ready|closed|error, message?}, transcript {role, text, final},
//   tool {name, result}, listening {on}, speaking {on}, thinking {on}, turn_complete, interrupted, notice {text}
import { wsBase } from '../config.js'
import { idToken } from '../data/auth.js'
import { langParam } from './lang.js'
import { AGENT_RATE, downsample, floatTo16, int16ToFloat, rms } from './pcm.js'

const SEND_EVERY = 640 // samples at 16 kHz = 40 ms
const ECHO_TAIL = 0.25 // s after the agent stops speaking before the mic is sent again (hands-free)

// getToken: where the socket token comes from (default the signed-in staff member's ID token; a front-desk call
// passes its caller token, C15). role: who is talking, for typed messages in the transcript.
export function createVoice({ onEvent, handsFree = true, lang = 'auto', getToken = idToken, role = 'mechanic' }) {
  let ws = null
  let connecting = false
  let mic = null
  let micCtx = null
  let micNode = null
  let outCtx = null
  let playhead = 0
  let sources = new Set()
  let talking = handsFree
  let pending = []
  let pendingLen = 0
  let micLevel = 0
  let closed = false
  let speakingTimer = null
  const said = {} // per role (mechanic/owner/agent): Live sends transcript chunks; screens get the text so far

  function sendAudio(frame16, flush = false) {
    if (frame16) {
      pending.push(frame16)
      pendingLen += frame16.length
    }
    if (!pendingLen || (pendingLen < SEND_EVERY && !flush)) return
    const all = new Int16Array(pendingLen)
    let o = 0
    for (const p of pending) { all.set(p, o); o += p.length }
    pending = []
    pendingLen = 0
    if (ws?.readyState === WebSocket.OPEN) ws.send(all.buffer)
  }

  // Hands-free on a laptop or phone speaker: the mic hears the agent's own voice, Gemini takes it as the
  // mechanic speaking and answers again (the reply is heard twice). So the mic is not sent while the agent
  // is speaking. Push-to-talk is not gated: pressing the button stops playback first (barge-in).
  function agentSpeaking() {
    return !!outCtx && sources.size > 0 && outCtx.currentTime < playhead + ECHO_TAIL
  }

  async function startMic() {
    mic = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    })
    micCtx = new AudioContext()
    await micCtx.audioWorklet.addModule('/mic-worklet.js')
    micNode = new AudioWorkletNode(micCtx, 'mic-capture')
    micNode.port.onmessage = (e) => {
      micLevel = rms(e.data)
      if (talking && !closed && !(handsFree && agentSpeaking())) sendAudio(floatTo16(downsample(e.data, micCtx.sampleRate)))
    }
    micCtx.createMediaStreamSource(mic).connect(micNode)
  }

  // Stop the mic, the playback and the socket. Safe to call more than once.
  function release() {
    if (micNode) micNode.port.onmessage = null
    mic?.getTracks().forEach((t) => t.stop())
    micCtx?.close().catch(() => {})
    stopPlayback()
    outCtx?.close().catch(() => {})
    if (ws) {
      ws.onmessage = null
      ws.onclose = null
      if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close()
    }
    mic = micCtx = micNode = outCtx = null
  }

  function play(buffer) {
    if (closed) return
    if (!outCtx) outCtx = new AudioContext({ sampleRate: AGENT_RATE })
    const samples = int16ToFloat(buffer)
    const audio = outCtx.createBuffer(1, samples.length, AGENT_RATE)
    audio.copyToChannel(samples, 0)
    const src = outCtx.createBufferSource()
    src.buffer = audio
    src.connect(outCtx.destination)
    playhead = Math.max(playhead, outCtx.currentTime + 0.03)
    src.start(playhead)
    playhead += audio.duration
    sources.add(src)
    src.onended = () => sources.delete(src)
    onEvent({ type: 'speaking', on: true })
    clearTimeout(speakingTimer)
    speakingTimer = setTimeout(() => onEvent({ type: 'speaking', on: false }), (playhead - outCtx.currentTime) * 1000 + 150)
  }

  function stopPlayback() {
    sources.forEach((s) => { try { s.stop() } catch { /* already stopped */ } })
    sources.clear()
    playhead = 0
    clearTimeout(speakingTimer)
    if (!closed) onEvent({ type: 'speaking', on: false })
  }

  function sendJson(msg) {
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg))
  }

  function onMessage(e) {
    if (typeof e.data !== 'string') return play(e.data)
    const msg = JSON.parse(e.data)
    if (msg.type === 'interrupted') stopPlayback()
    if (msg.type === 'tool') onEvent({ type: 'thinking', on: false })
    if (msg.type === 'blocked') { // C20 topic guard: an off-topic answer was cut off (or typed text never sent)
      stopPlayback()
      said.agent = ''
      onEvent({ type: 'thinking', on: false })
      return onEvent({ type: 'blocked', typed: !!msg.typed })
    }
    if (msg.type === 'ignored') { // push-to-talk turn with no speech: nothing was sent to the agent
      onEvent({ type: 'thinking', on: false })
      return onEvent({ type: 'note', text: "Didn't catch that. Hold the button and speak." })
    }
    if (msg.type === 'transcript') {
      // The final event carries the whole utterance; partial ones are chunks to append.
      const text = msg.final ? msg.text : (said[msg.role] = (said[msg.role] || '') + msg.text)
      if (msg.final) said[msg.role] = ''
      if (msg.role === 'agent') onEvent({ type: 'thinking', on: false })
      return onEvent({ ...msg, text: text.trim() })
    }
    if (msg.type === 'turn_complete') Object.keys(said).forEach((k) => { said[k] = '' })
    onEvent(msg)
  }

  return {
    demo: false,
    // One socket per client, ever: a second connect() (double tap, React StrictMode) does nothing.
    async connect() {
      if (connecting || ws || closed) return
      connecting = true
      onEvent({ type: 'status', status: 'connecting' })
      try {
        await startMic()
      } catch {
        release()
        onEvent({ type: 'status', status: 'error', message: 'Microphone blocked. Allow it in the browser settings.' })
        return
      }
      const token = await getToken()
      if (closed) return release()
      ws = new WebSocket(`${wsBase()}/ws/voice?token=${encodeURIComponent(token)}${handsFree ? '' : '&ptt=1'}${langParam(lang)}`)
      ws.binaryType = 'arraybuffer'
      ws.onopen = () => onEvent({ type: 'status', status: 'ready' })
      ws.onmessage = onMessage
      ws.onclose = (e) => {
        release()
        closed = true
        const message = e.code === 4401 || e.code === 4403 ? (role === 'caller' ? 'The call ended. Call again if you need more help.' : 'Signed out. Please sign in again.')
          : e.code === 4409 ? 'Opened on another screen.' : 'Connection lost.'
        onEvent({ type: 'status', status: 'error', message, code: e.code })
      }
    },
    startTalking() {
      stopPlayback() // barge in
      talking = true
      if (!handsFree) sendJson({ type: 'start' })
      onEvent({ type: 'listening', on: true })
    },
    stopTalking() {
      if (handsFree) return
      talking = false
      sendAudio(null, true) // the last few ms of the turn
      sendJson({ type: 'stop' })
      onEvent({ type: 'listening', on: false })
      onEvent({ type: 'thinking', on: true })
    },
    mute(on) {
      talking = !on
      onEvent({ type: 'listening', on: !on })
    },
    sendText(text) {
      sendJson({ type: 'text', text })
      onEvent({ type: 'transcript', role, text, final: true })
      onEvent({ type: 'thinking', on: true })
    },
    level() {
      return talking ? Math.min(1, micLevel * 6) : 0
    },
    nextLine() {
      return ''
    },
    close() {
      if (closed) return
      closed = true
      release()
      onEvent({ type: 'status', status: 'closed' })
    },
  }
}
