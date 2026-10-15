// "Call the garage" (C15): a voice call to the AI front desk, from the customer page or the landing page.
// Same voice client and gateway as the staff screens; the call token (from the backend) makes the gateway pick the
// front desk agent. Push to talk, like the owner's panel. Shows the status in words, never a number pad.
import { useCallback, useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { DEMO } from '../config.js'
import { Bubble, KeyboardIcon, Orb } from '../voice/parts.jsx'
import { useSpaceToTalk, useVoice } from '../voice/useVoice.js'

export function CallButton({ getToken, label = 'Call the garage', className = 'btn btn-primary', garage }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className={className} onClick={() => setOpen(true)}><PhoneIcon /> {label}</button>
      {/* On document.body: the panel is fixed and must not be clipped by the page layout around the button */}
      {open && createPortal(<CallPanel getToken={getToken} garage={garage} onClose={() => setOpen(false)} />, document.body)}
    </>
  )
}

export default function CallPanel({ getToken, garage = 'the garage', onClose }) {
  // The page around the button re-renders on every live update with a new getToken function; a stable one keeps
  // the call going (a new getToken would restart it as a new call).
  const tokenFn = useRef(getToken)
  tokenFn.current = getToken
  const stableGetToken = useCallback(() => tokenFn.current(), [])
  const { status, items, flags, voice, start } = useVoice({ handsFree: false, role: 'caller', getToken: stableGetToken })
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const feed = useRef(null)
  const ready = status.status === 'ready'
  useSpaceToTalk(voice, ready && !typing)

  useEffect(() => { start() }, [start])
  useEffect(() => { feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' }) }, [items])
  useEffect(() => {
    const esc = (e) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', esc)
    return () => window.removeEventListener('keydown', esc)
  }, [onClose])

  const mode = !ready ? 'offline' : flags.speaking ? 'speaking' : flags.thinking ? 'thinking' : flags.listening ? 'listening' : 'idle'
  const label = {
    offline: status.status === 'connecting' ? 'Calling…' : status.status === 'error' ? 'Call again' : 'Call',
    speaking: 'Speaking…',
    thinking: 'One moment…',
    listening: 'Listening… let go to send',
    idle: 'Hold to talk',
  }[mode]
  const hint = DEMO && ready ? voice.current?.nextLine() : ''

  function down(e) {
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* synthetic events */ }
    voice.current?.startTalking()
  }

  return (
    <section className="owner-voice call-panel theme-dark pop" role="dialog" aria-label={`Call ${garage}`}>
      <header className="row between">
        <div className="stack" style={{ '--gap': '0px' }}>
          <strong>Calling {garage}</strong>
          <span className="muted small">AI front desk · status, quotes, prices, bookings</span>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => { voice.current?.close(); onClose() }}>End call</button>
      </header>

      <div className="feed-voice" ref={feed} aria-live="polite">
        {status.status === 'error' && <div className="note fade">{status.message}</div>}
        {items.length === 0 && status.status !== 'error' && (
          <div className="voice-empty fade">
            <p className="muted small">“Is my bike ready?”</p>
            <p className="muted small">“How much for a clutch plate change on a Splendor?”</p>
            <p className="muted small">“Can I bring it in tomorrow at 10?”</p>
          </div>
        )}
        {items.map((it) => <Bubble key={it.id} it={it} />)}
        {flags.thinking && <div className="bubble bubble-agent typing" aria-label="Working"><span /><span /><span /></div>}
      </div>

      <footer className="voice-bottom">
        {hint && <button className="hint fade" key={hint} onClick={() => voice.current.sendText(hint)}>Say: “{hint}”</button>}
        {typing ? (
          <form className="type-row fade" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { voice.current.sendText(text.trim()); setText('') } }}>
            <input className="input grow" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Type instead" />
            <button className="btn btn-accent" disabled={!ready}>Send</button>
            <button type="button" className="btn btn-ghost" onClick={() => setTyping(false)} aria-label="Stop typing">✕</button>
          </form>
        ) : (
          <div className="orb-row">
            <span />
            <Orb voice={voice} ready={ready} mode={mode} label={label} status={status} startLabel="Call"
              onStart={start} onDown={down} onUp={() => voice.current?.stopTalking()} />
            <button className="side-btn" onClick={() => setTyping(true)} aria-label="Type instead" disabled={!ready}><KeyboardIcon /></button>
          </div>
        )}
      </footer>
    </section>
  )
}

export function PhoneIcon() {
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z" /></svg>
}

