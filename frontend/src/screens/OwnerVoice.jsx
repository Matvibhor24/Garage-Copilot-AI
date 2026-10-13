// Owner: a mic button on the dashboard that opens a voice panel to ask about the day
// ("How much did we make today?"). Same voice client and gateway as the mechanic; the backend
// picks the owner agent from the token. Push to talk: the owner is usually at a desk or counter.
import { useEffect, useRef, useState } from 'react'
import { DEMO } from '../config.js'
import { MicIcon } from './Home.jsx'
import { Bubble, KeyboardIcon, Orb } from '../voice/parts.jsx'
import { useSpaceToTalk, useVoice } from '../voice/useVoice.js'

export default function OwnerVoice() {
  const [open, setOpen] = useState(false)
  return (
    <>
      {!open && (
        <button className="btn btn-primary voice-fab pop" onClick={() => setOpen(true)} aria-label="Ask GarageCopilot">
          <MicIcon /> Ask
        </button>
      )}
      {open && <VoicePanel onClose={() => setOpen(false)} />}
    </>
  )
}

function VoicePanel({ onClose }) {
  const { status, items, flags, voice, start } = useVoice({ handsFree: false, role: 'owner' })
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const feed = useRef(null)
  const ready = status.status === 'ready'
  useSpaceToTalk(voice, ready && !typing)

  useEffect(() => { start() }, [start])
  useEffect(() => { feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' }) }, [items])
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape' && !document.querySelector('dialog[open]')) onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const mode = !ready ? 'offline' : flags.speaking ? 'speaking' : flags.thinking ? 'thinking' : flags.listening ? 'listening' : 'idle'
  const label = {
    offline: status.status === 'connecting' ? 'Connecting…' : 'Start',
    speaking: 'Speaking…',
    thinking: 'Checking…',
    listening: 'Listening… let go to send',
    idle: 'Hold to ask',
  }[mode]
  const hint = DEMO && ready ? voice.current?.nextLine() : ''

  function down(e) {
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* synthetic events */ }
    voice.current?.startTalking()
  }

  return (
    <section className="owner-voice theme-dark pop" aria-label="Ask GarageCopilot">
      <header className="row between">
        <div className="stack" style={{ '--gap': '0px' }}>
          <strong>Ask GarageCopilot</strong>
          <span className="muted small">Jobs, approvals, money, stock</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={onClose}>Close</button>
      </header>

      <div className="feed-voice" ref={feed} aria-live="polite">
        {items.length === 0 && (
          <div className="voice-empty fade">
            <p className="muted small">“How many bikes are in today?”</p>
            <p className="muted small">“What's waiting for approval?”</p>
          </div>
        )}
        {items.map((it) => <Bubble key={it.id} it={it} />)}
        {flags.thinking && <div className="bubble bubble-agent typing" aria-label="Working"><span /><span /><span /></div>}
      </div>

      <footer className="voice-bottom">
        {hint && <button className="hint fade" key={hint} onClick={() => voice.current.sendText(hint)}>Ask: “{hint}”</button>}
        {typing ? (
          <form className="type-row fade" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { voice.current.sendText(text.trim()); setText('') } }}>
            <input className="input grow" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Type a question" />
            <button className="btn btn-accent" disabled={!ready}>Send</button>
            <button type="button" className="btn btn-ghost" onClick={() => setTyping(false)} aria-label="Stop typing">✕</button>
          </form>
        ) : (
          <div className="orb-row">
            <span />
            <Orb voice={voice} ready={ready} mode={mode} label={label} status={status} startLabel="Start talking"
              onStart={start} onDown={down} onUp={() => voice.current?.stopTalking()} />
            <button className="side-btn" onClick={() => setTyping(true)} aria-label="Type a question" disabled={!ready}><KeyboardIcon /></button>
          </div>
        )}
      </footer>
    </section>
  )
}
