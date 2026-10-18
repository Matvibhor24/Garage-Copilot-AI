// Mechanic: name + PIN on the shared garage phone, then a hands-free voice screen.
import { useEffect, useRef, useState } from 'react'
import { api } from '../data/api.js'
import { shrinkPhoto } from '../photo.js'
import { session, signInWithPin, signOut } from '../data/auth.js'
import { useLiveView } from '../data/live.js'
import { DEMO, TRY } from '../config.js'
import { plate, STAGE_LABEL } from '../format.js'
import { Brand, Spinner, useToast } from '../ui.jsx'
import { Bubble, CameraIcon, KeyboardIcon, LangPicker, Orb } from '../voice/parts.jsx'
import { readLang, saveLang } from '../voice/lang.js'
import { useSpaceToTalk, useVoice } from '../voice/useVoice.js'
import TryGuide from './TryGuide.jsx'

// Shift policy (shared garage phone): the voice screen only shows for a mechanic who signed in on this screen.
// Leaving it in any way signs them out (Back/Forward or a link inside the app, going to another site and
// coming back, a page restored from the back-forward cache). Only a reload of the mechanic screen keeps the shift.
const LEFT = 'gc.mechanic-left'
let mounted = 0
let bootChecked = false

function mechanicSession() {
  const s = session()?.role === 'mechanic' ? session() : null
  if (!bootChecked) { // first look in this page load: was the screen left (pagehide) and not just reloaded?
    bootChecked = true
    const left = sessionStorage.getItem(LEFT)
    sessionStorage.removeItem(LEFT)
    const reload = performance.getEntriesByType?.('navigation')[0]?.type === 'reload'
    if (s && left && !reload) {
      signOut()
      return null
    }
  }
  return s
}

export default function Mechanic() {
  const [me, setMe] = useState(mechanicSession)
  useEffect(() => {
    document.documentElement.dataset.theme = 'dark'
    mounted += 1
    const left = () => { if (session()?.role === 'mechanic') sessionStorage.setItem(LEFT, '1') }
    const back = (e) => { // restored from the back-forward cache: history navigation, so the shift is over
      if (!e.persisted) return
      sessionStorage.removeItem(LEFT)
      signOut()
      setMe(null)
    }
    window.addEventListener('pagehide', left)
    window.addEventListener('pageshow', back)
    return () => {
      delete document.documentElement.dataset.theme
      window.removeEventListener('pagehide', left)
      window.removeEventListener('pageshow', back)
      mounted -= 1
      // Left the screen inside the app. (The timeout lets React StrictMode's test remount count as staying.)
      setTimeout(() => { if (!mounted && session()?.role === 'mechanic') signOut() }, 0)
    }
  }, [])
  return me ? <VoiceScreen me={me} onSignOut={async () => { await signOut(); setMe(null) }} /> : <PinSignIn onDone={setMe} />
}

// ---------------------------------------------------------------- sign in

function PinSignIn({ onDone }) {
  const [garage, setGarage] = useState(() => localStorage.getItem('gc.garage') || new URLSearchParams(location.search).get('g') || 'shree-auto')
  const [name, setName] = useState('')
  const [pin, setPin] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  async function submit(fullPin) {
    setBusy(true)
    setError('')
    try {
      localStorage.setItem('gc.garage', garage)
      onDone(await signInWithPin(api, garage, name, fullPin))
    } catch (e) {
      setError(e.message)
      setPin('')
    } finally {
      setBusy(false)
    }
  }

  function press(d) {
    if (busy || !name.trim()) return
    if (d === 'del') return setPin((p) => p.slice(0, -1))
    const next = (pin + d).slice(0, 4)
    setPin(next)
    if (next.length === 4) submit(next)
  }

  return (
    <main className="page page-narrow pin-screen">
      <header className="topbar"><Brand /></header>
      <section className="stack enter" style={{ '--gap': '22px' }}>
        <div className="stack" style={{ '--gap': '6px' }}>
          <span className="eyebrow">Mechanic</span>
          <h1>Who's working?</h1>
        </div>
        {TRY && !DEMO && (
          <div className="try-login small">
            <span>Trying GarageCopilot? Sign in as <strong>{TRY.mechanic}</strong>, PIN <strong className="mono">{TRY.pin}</strong>.</span>
            <button className="btn btn-sm" onClick={() => setName(TRY.mechanic)}>Fill in</button>
          </div>
        )}
        <div className="field">
          <label htmlFor="name">Your name</label>
          <input id="name" className="input" autoComplete="username" value={name} onChange={(e) => setName(e.target.value)} placeholder={DEMO ? 'Raju' : 'Name'} />
        </div>
        <details className="small muted">
          <summary>Garage: <span className="mono">{garage}</span></summary>
          <input className="input" style={{ marginTop: 8 }} value={garage} onChange={(e) => setGarage(e.target.value.trim())} aria-label="Garage id" />
        </details>

        <div className={`pin-dots ${error ? 'shake' : ''}`} aria-label={`${pin.length} of 4 digits`}>
          {[0, 1, 2, 3].map((i) => <span key={i} className={i < pin.length ? 'on' : ''} />)}
        </div>
        <p className="pin-msg small" role="alert">{busy ? <Spinner /> : error || (DEMO ? 'Demo: Raju, PIN 1234' : 'Enter your 4-digit PIN')}</p>

        <div className="keypad">
          {['1', '2', '3', '4', '5', '6', '7', '8', '9', '', '0', 'del'].map((k) => k === '' ? <span key="blank" /> : (
            <button key={k} className="key" onClick={() => press(k)} disabled={busy || !name.trim()} aria-label={k === 'del' ? 'Delete' : k}>
              {k === 'del' ? '⌫' : k}
            </button>
          ))}
        </div>
      </section>
    </main>
  )
}

// ---------------------------------------------------------------- voice

function VoiceScreen({ me, onSignOut }) {
  const toast = useToast()
  const [handsFree, setHandsFree] = useState(() => localStorage.getItem('gc.handsfree') !== '0')
  const [lang, setLang] = useState(() => readLang('mechanic'))
  const { status, items, flags, currentJob, setCurrentJob, voice, start, setItems } = useVoice({ handsFree, role: 'mechanic', lang })
  const [typing, setTyping] = useState(false)
  const [text, setText] = useState('')
  const [muted, setMuted] = useState(false)
  const [menu, setMenu] = useState(false)
  const [guide, setGuide] = useState(() => {
    try { return !!TRY && !DEMO && localStorage.getItem('gc.try-seen') !== '1' } catch { return !!TRY && !DEMO }
  })
  const feed = useRef(null)
  const photo = useRef(null)
  const g = me.garage
  const jobs = useLiveView(() => api('/api/jobs'), { watch: [`garages/${g}/jobs`, `garages/${g}/quotes`] })
  // A closed job drops out of the open list: keep showing it, marked done.
  const lastJob = useRef(null)
  const openJob = jobs.data?.find((j) => j.id === currentJob) || null
  if (openJob) lastJob.current = openJob
  const job = openJob || (jobs.data && lastJob.current?.id === currentJob ? { ...lastJob.current, status: 'done', stage: 'done', pending_quote: null } : null)
  const ready = status.status === 'ready'

  // Until the agent names a job, show the mechanic's most recent open one.
  useEffect(() => {
    if (currentJob || !jobs.data) return
    const mine = jobs.data.filter((j) => j.mechanic_name === me.name).sort((a, b) => (b.stage_started_at || '').localeCompare(a.stage_started_at || ''))
    if (mine[0]) setCurrentJob(mine[0].id)
  }, [jobs.data, currentJob, setCurrentJob, me.name])

  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' })
  }, [items])

  useSpaceToTalk(voice, ready && !typing)

  const pushToTalk = DEMO || !handsFree
  const mode = !ready ? 'offline' : flags.speaking ? 'speaking' : flags.thinking ? 'thinking' : flags.listening && !muted ? 'listening' : 'idle'
  const label = {
    offline: status.status === 'connecting' ? 'Connecting…' : 'Start',
    speaking: 'Speaking…',
    thinking: 'Working on it…',
    listening: pushToTalk ? 'Listening… let go to send' : 'Listening',
    idle: pushToTalk ? 'Hold to talk' : muted ? 'Muted · tap to listen' : 'Listening',
  }[mode]

  function orbDown(e) {
    if (!ready) return
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* synthetic events */ }
    if (pushToTalk) voice.current.startTalking()
  }
  function orbUp() {
    if (!ready) return
    if (pushToTalk) voice.current.stopTalking()
    else {
      voice.current.mute(!muted)
      setMuted(!muted)
    }
  }

  async function sendPhoto(file) {
    if (!file) return
    if (!currentJob) return toast('Open a job first')
    try {
      toast('Sending photo…')
      const photo = await shrinkPhoto(file) // a small JPEG: HEIC and huge camera files were rejected (C21)
      await api(`/api/jobs/${currentJob}/photos`, { method: 'POST', rawBody: photo, contentType: photo.type || file.type || 'image/jpeg' })
      setItems((l) => [...l, { id: Math.random(), kind: 'note', text: `Photo added to ${currentJob}`, final: true }])
      toast(`Photo added to ${currentJob}`)
    } catch (e) {
      toast(e.message)
    }
  }

  function switchMode() {
    const next = !handsFree
    localStorage.setItem('gc.handsfree', next ? '1' : '0')
    voice.current?.close()
    setHandsFree(next)
    toast(next ? 'Hands-free: just talk' : 'Push to talk: hold the button')
  }

  // A pinned language is sent when the session starts, so changing it starts a fresh one.
  const restart = useRef(false)
  function switchLang(next) {
    saveLang('mechanic', next)
    restart.current = ready
    voice.current?.close()
    setLang(next)
    toast(next === 'auto' ? 'Replies follow the language you speak' : 'Replies pinned to that language')
  }
  useEffect(() => { if (restart.current) { restart.current = false; start() } }, [start])

  const hint = DEMO && ready ? voice.current?.nextLine() : ''

  return (
    <main className="voice theme-dark">
      {guide && (
        <TryGuide
          onClose={() => { setGuide(false); try { localStorage.setItem('gc.try-seen', '1') } catch { /* private mode */ } }}
          onSay={ready ? (line) => voice.current.sendText(line) : null} />
      )}
      <header className="voice-top">
        <Brand to="/mechanic" live={mode === 'listening' || mode === 'speaking'} />
        <div className="row" style={{ '--gap': '8px' }}>
          {TRY && !DEMO && <button className="btn btn-ghost btn-sm" onClick={() => setGuide(true)}>Try a demo</button>}
          <LangPicker value={lang} onChange={switchLang} />
          <span className={`chip ${ready ? 'chip-ok' : status.status === 'error' ? 'chip-bad' : ''}`}>
            <span className={`dot ${ready ? 'live-dot' : ''}`} />{ready ? me.name : status.status === 'error' ? 'Offline' : me.name}
          </span>
          <button className="btn btn-ghost icon-btn" onClick={() => setMenu((m) => !m)} aria-label="Menu" aria-expanded={menu}>⋯</button>
        </div>
        {menu && (
          <div className="menu pop" role="menu">
            {!DEMO && <button role="menuitem" onClick={() => { setMenu(false); switchMode() }}>{handsFree ? 'Switch to push-to-talk' : 'Switch to hands-free'}</button>}
            {DEMO && <button role="menuitem" onClick={async () => { (await import('../demo/voice.js')).resetDemo(); location.reload() }}>Reset demo</button>}
            <button role="menuitem" onClick={onSignOut}>Sign out</button>
          </div>
        )}
      </header>

      {/* Phones: job strip on top. Wide screens: a side panel with the current job and the open jobs. */}
      <div className="voice-body">
        <aside className="voice-side" aria-label="Jobs">
          <JobStrip job={job} />
          <OpenJobs jobs={jobs.data} current={currentJob} />
        </aside>

        <div className="voice-main">
          <section className="feed-voice" ref={feed} aria-live="polite">
            {items.length === 0 && (
              <div className="voice-empty fade">
                <p className="muted">{ready ? (pushToTalk ? 'Hold the button and talk.' : 'Just talk. I am listening.') : 'Start your shift to talk to GarageCopilot.'}</p>
                <p className="muted small">“New bike, Splendor Plus, MH12 AB 1234, owner Ramesh…”</p>
              </div>
            )}
            {items.map((it) => <Bubble key={it.id} it={it} />)}
            {flags.thinking && <div className="bubble bubble-agent typing" aria-label="Working"><span /><span /><span /></div>}
          </section>

          <footer className="voice-bottom">
            {hint && <button className="hint fade" key={hint} onClick={() => voice.current.sendText(hint)}>Say: “{hint}”</button>}
            {typing ? (
              <form className="type-row fade" onSubmit={(e) => { e.preventDefault(); if (text.trim()) { voice.current.sendText(text.trim()); setText('') } }}>
                <input className="input grow" autoFocus value={text} onChange={(e) => setText(e.target.value)} placeholder="Type instead of talking" />
                <button className="btn btn-accent" disabled={!ready}>Send</button>
                <button type="button" className="btn btn-ghost" onClick={() => setTyping(false)}>✕</button>
              </form>
            ) : (
              <div className="orb-row">
                <button className="side-btn" onClick={() => photo.current?.click()} aria-label="Take a photo" disabled={!ready}><CameraIcon /></button>
                <Orb voice={voice} ready={ready} mode={mode} label={label} status={status} startLabel="Start shift"
                  onStart={start} onDown={orbDown} onUp={orbUp} />
                <button className="side-btn" onClick={() => setTyping(true)} aria-label="Type a message" disabled={!ready}><KeyboardIcon /></button>
              </div>
            )}
            <input ref={photo} type="file" accept="image/*" capture="environment" hidden onChange={(e) => { sendPhoto(e.target.files[0]); e.target.value = '' }} />
          </footer>
        </div>
      </div>
    </main>
  )
}

function JobStrip({ job }) {
  if (!job) return <div className="job-strip job-strip-empty muted small">No job open yet</div>
  const waiting = !!job.pending_quote
  return (
    <div className="job-strip pop" key={job.id + job.stage + waiting}>
      <div className="grow stack" style={{ '--gap': '0px', minWidth: 0 }}>
        <strong className="ellipsis">{job.vehicle} · {job.owner}</strong>
        <span className="muted small ellipsis"><span className="mono">{plate(job.plate)}</span> · {job.id}</span>
      </div>
      <span className={`chip ${waiting ? 'chip-warn' : job.status === 'done' ? 'chip-ok' : 'chip-accent'}`}>
        {waiting ? 'Waiting on customer' : job.status === 'done' ? 'Closed' : STAGE_LABEL[job.stage] || job.stage}
      </span>
      {job.customer_url && (
        <a className="btn btn-ghost btn-sm" href={job.customer_url} target="_blank" rel="noopener noreferrer"
          title="Open the page the customer sees">Customer view ↗</a>
      )}
    </div>
  )
}

// Wide screens only (hidden on phones by CSS): every open job, the one being talked about highlighted.
function OpenJobs({ jobs, current }) {
  if (!jobs) return null
  return (
    <section className="voice-jobs">
      <h3 className="eyebrow">Open jobs · {jobs.length}</h3>
      {jobs.length === 0 ? <p className="muted small">None right now.</p> : (
        <ul>
          {jobs.map((j) => (
            <li key={j.id} className={j.id === current ? 'on' : ''}>
              <div className="grow stack" style={{ '--gap': '0px', minWidth: 0 }}>
                <strong className="ellipsis">{j.vehicle} · {j.owner}</strong>
                <span className="muted small ellipsis"><span className="mono">{j.id}</span> · {j.mechanic_name}</span>
              </div>
              <span className={`chip ${j.pending_quote ? 'chip-warn' : ''}`}>{j.pending_quote ? 'Waiting' : STAGE_LABEL[j.stage] || j.stage}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
