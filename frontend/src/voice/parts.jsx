// Pieces shared by the mechanic screen and the owner's voice panel.
import { useEffect, useRef } from 'react'
import { Spinner } from '../ui.jsx'
import { LANGS } from './lang.js'

// The big talk button. It reacts to the mic level every frame (--lvl) and shows the agent's state.
export function Orb({ voice, ready, mode, label, status, startLabel = 'Start', onStart, onDown, onUp }) {
  const orb = useRef(null)
  useEffect(() => {
    let raf
    const tick = () => {
      const lvl = voice.current?.level() || 0
      orb.current?.style.setProperty('--lvl', lvl.toFixed(3))
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [voice])

  return (
    <div className="orb-wrap">
      {ready ? (
        <button ref={orb} className={`orb orb-${mode}`} onPointerDown={onDown} onPointerUp={onUp} onPointerCancel={onUp}
          onContextMenu={(e) => e.preventDefault()} aria-label={label}>
          <span className="orb-ring" /><span className="orb-ring r2" /><span className="orb-core" />
        </button>
      ) : (
        <button ref={orb} className="orb orb-offline" onClick={onStart} disabled={status.status === 'connecting'} aria-label={startLabel}>
          <span className="orb-core" />{status.status === 'connecting' ? <Spinner /> : <span className="orb-start">Start</span>}
        </button>
      )}
      <span className="orb-label" key={label}>{status.status === 'error' ? status.message : label}</span>
    </div>
  )
}

export function Bubble({ it }) {
  if (it.kind === 'tool') return <div className={`tool-chip fade ${it.error ? 'tool-error' : ''}`}><span>{it.error ? '!' : '✓'}</span>{it.text}</div>
  if (it.kind === 'note') return <div className="note fade">{it.text}</div>
  if (it.kind === 'notice') return <div className="bubble bubble-notice pop"><span className="eyebrow" style={{ color: 'inherit' }}>Update</span>{it.text}</div>
  return <div className={`bubble bubble-${it.kind === 'agent' ? 'agent' : 'mechanic'} ${it.final ? '' : 'partial'}`}>{it.text}</div>
}

export function CameraIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><path d="M4 8h3l2-3h6l2 3h3v11H4z" /><circle cx="12" cy="13" r="3.5" /></svg>
}
export function KeyboardIcon() {
  return <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="2" y="6" width="20" height="12" rx="3" /><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10" /></svg>
}

// Reply language: Auto (follow the speaker) or pinned (C11).
export function LangPicker({ value, onChange }) {
  return (
    <select className="lang-pick" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Reply language"
      title="Reply language: Auto follows the language you speak">
      {LANGS.map((l) => <option key={l.code} value={l.code}>{l.code === 'auto' ? 'Auto language' : l.label}</option>)}
    </select>
  )
}
