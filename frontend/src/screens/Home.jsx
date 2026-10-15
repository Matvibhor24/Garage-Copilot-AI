// Landing page (C16): what GarageCopilot is in a few seconds, mostly pictures, then "Try it".
// No images or heavy libraries: inline SVG and CSS. Respects reduced motion (the hero shows all four steps at once).
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../data/api.js'
import { Brand } from '../ui.jsx'
import { DEMO, FRONT_DESK_GARAGE, FRONT_DESK_GARAGE_NAME } from '../config.js'
import { CallButton } from './CallPanel.jsx'
import '../landing.css'

const FLOW = [
  { key: 'speak', label: 'Mechanic speaks' },
  { key: 'job', label: 'Job card appears' },
  { key: 'approve', label: 'Customer approves' },
  { key: 'floor', label: 'Owner sees it live' },
]

export default function Home() {
  return (
    <main className="landing">
      <header className="topbar landing-top">
        <Brand live />
        <nav className="row" style={{ '--gap': '8px' }} aria-label="Sign in">
          {DEMO && <span className="chip chip-accent">Demo mode</span>}
          <a className="btn btn-primary btn-sm" href="#try">Try it</a>
        </nav>
      </header>

      <section className="lp-hero">
        <div className="lp-hero-text enter">
          <span className="eyebrow">For India's two-wheeler and car garages</span>
          <h1>The AI co-worker for India's garages</h1>
          <p className="lp-lead">Mechanics talk, it does the paperwork, customers approve from their phone.</p>
          <div className="row wrap" style={{ '--gap': '10px' }}>
            <a className="btn btn-accent btn-lg" href="#try">Try it now</a>
            <a className="btn btn-lg btn-ghost" href="#how">How it works</a>
          </div>
        </div>
        <FlowLoop />
      </section>

      <section className="lp-section" aria-labelledby="lp-problem">
        <h2 id="lp-problem" className="lp-h2">The problem</h2>
        <div className="lp-cards3">
          <ProblemCard art={<GreasyHands />} title="Greasy hands, ringing phone">Every stock check or “can we go ahead?” call stops the work.</ProblemCard>
          <ProblemCard art={<SurpriseBill />} title="A worried customer">Nobody likes a surprise on the bill at pickup time.</ProblemCard>
          <ProblemCard art={<BlindOwner />} title="An owner in the dark">Which bike is where, waiting on what? Nobody knows without walking the floor.</ProblemCard>
        </div>
      </section>

      <section className="lp-section" id="how" aria-labelledby="lp-how">
        <h2 id="lp-how" className="lp-h2">How it works</h2>
        <HowDiagram />
      </section>

      <section className="lp-section" aria-labelledby="lp-diff">
        <h2 id="lp-diff" className="lp-h2">What makes it different</h2>
        <div className="lp-tiles">
          <Tile icon="🎧" title="Hands-free, in their language">Hindi, Marathi, English or Hinglish. The headset answers in the language you speak.</Tile>
          <Tile icon="✅" title="Nothing extra without an OK">Extra work over the garage's limit waits for the customer's tap on their phone.</Tile>
          <Tile icon="📖" title="Answers from the manual">Specs come from the vehicle's own manual, with the page. Never a guess.</Tile>
          <Tile icon="🧊" title="Live 3D view of the garage">The owner sees every vehicle at its bay, and who is working on it.</Tile>
        </div>
      </section>

      <section className="lp-section" id="try" aria-labelledby="lp-try">
        <h2 id="lp-try" className="lp-h2">Try it</h2>
        <p className="muted lp-sub">{DEMO
          ? 'Demo mode: sample data in this browser. Start with the mechanic, then open the customer page and the owner.'
          : 'Sign in as a mechanic or the owner. Customers get their link on WhatsApp.'}</p>
        <div className="lp-cards3">
          <TryCard step="1" to="/mechanic" title="Mechanic" icon={<MicIcon />} cta="Open the mechanic screen"
            lines={DEMO
              ? ['Sign in as Raju, PIN 1234.', 'Hold the orb and say: “New bike, Splendor Plus, MH12 AB 1234, owner Ramesh, clutch slipping.”', 'Keep holding and talking: service, stock check, the quote, washing, job done.']
              : ['Sign in with your name and PIN.', 'Hold the orb and say: “New bike, Splendor Plus, MH12 AB 1234, owner Ramesh…”']} />
          {DEMO ? (
            <TryCard step="2" to="/j/demo-J-1042" title="Customer" icon={<PhoneIcon />} cta="Open Ramesh's page"
              lines={['After the mechanic sends the quote, open Ramesh\'s page.', 'Approve the ₹950 quote with one tap and watch the timeline move.', 'Switch to हिंदी, or tap “Call the garage”.']} />
          ) : (
            <TryCard step="2" title="Customer" icon={<PhoneIcon />}
              lines={['Customers get a private link on WhatsApp when their vehicle is checked in.', 'They approve extra work there with one tap, and can call the garage.']} />
          )}
          <div className="lp-col">
            <TryCard step="3" to="/owner" title="Owner" icon={<GridIcon />} cta="Open the owner dashboard"
              lines={['Watch the floor live: every vehicle at its bay, in 3D.', 'Answer the reorder question, see calls, ask “How much did we make today?”']} />
            <LandingCall />
          </div>
        </div>
      </section>

      <footer className="lp-footer">
        <span>Built on Gemini · ADK · Cloud Run · Firestore</span>
        <span className="muted">GarageCopilot · Google AI Builders Cup 2026</span>
      </footer>
    </main>
  )
}

// ---------------------------------------------------------------- hero animation

function FlowLoop() {
  const reduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  const [step, setStep] = useState(reduced ? FLOW.length : 0)
  useEffect(() => {
    if (reduced) return
    const t = setInterval(() => setStep((s) => (s + 1) % (FLOW.length + 1)), 1900)
    return () => clearInterval(t)
  }, [reduced])
  const on = (i) => step > i
  return (
    <div className={`flow ${reduced ? 'flow-static' : ''}`} role="img" aria-label="The mechanic speaks, a job card appears, the customer approves on their phone, and the owner's floor updates.">
      <div className={`flow-step ${on(0) ? 'on' : ''}`}>
        <div className="flow-mic"><span /><span /><span /><span /><span /></div>
        <p className="flow-bubble">“New bike, Splendor Plus, owner Ramesh…”</p>
      </div>
      <div className={`flow-step ${on(1) ? 'on' : ''}`}>
        <div className="flow-card">
          <span className="mono small">J-1042</span>
          <strong>Splendor Plus</strong>
          <span className="chip chip-accent">In service</span>
        </div>
      </div>
      <div className={`flow-step ${on(2) ? 'on' : ''}`}>
        <div className="flow-phone">
          <span className="small muted">Extra work found</span>
          <strong>₹950</strong>
          <span className={`flow-approve ${on(2) ? 'done' : ''}`}>{on(2) ? '✓ Approved' : 'Approve'}</span>
        </div>
      </div>
      <div className={`flow-step ${on(3) ? 'on' : ''}`}>
        <div className="flow-floor">
          {[0, 1, 2, 3].map((i) => <span key={i} className={`bay ${i === 1 ? 'bay-hot' : ''}`} />)}
          <span className="flow-dot" />
        </div>
      </div>
      <ol className="flow-labels">
        {FLOW.map((f, i) => <li key={f.key} className={on(i) ? 'on' : ''}>{f.label}</li>)}
      </ol>
    </div>
  )
}

// ---------------------------------------------------------------- sections

function ProblemCard({ art, title, children }) {
  return (
    <article className="card lp-problem">
      <div className="lp-art" aria-hidden="true">{art}</div>
      <h3>{title}</h3>
      <p className="muted">{children}</p>
    </article>
  )
}

function Tile({ icon, title, children }) {
  return (
    <article className="card lp-tile">
      <span className="lp-tile-icon" aria-hidden="true">{icon}</span>
      <h3>{title}</h3>
      <p className="muted small">{children}</p>
    </article>
  )
}

function TryCard({ step, to, title, icon, lines, cta }) {
  const body = (
    <>
      <div className="row between">
        <span className="role-icon" aria-hidden="true">{icon}</span>
        <span className="lp-step">{step}</span>
      </div>
      <h3>{title}</h3>
      <ul className="lp-try-lines">{lines.map((l) => <li key={l}>{l}</li>)}</ul>
      {cta && <span className="lp-cta">{cta} →</span>}
    </>
  )
  return to
    ? <Link to={to} className="card lp-try" viewTransition aria-label={`${title}: ${cta}`}>{body}</Link>
    : <article className="card lp-try">{body}</article>
}

// Call the garage from the website (C15): the number is typed, so the front desk shares no job details.
function LandingCall() {
  const [phone, setPhone] = useState(DEMO ? '+91 98111 12222' : '+91 ')
  const valid = phone.replace(/\D/g, '').length >= 12 || phone.replace(/\D/g, '').length === 10
  return (
    <div className="card lp-call">
      <div className="stack" style={{ '--gap': '4px' }}>
        <h3>Call the garage</h3>
        <p className="muted small">No job needed: ask the AI front desk about prices, book a drop-off or ask for a callback. The owner sees every call on the dashboard. (For your vehicle's status, call from the link the garage sent you.)</p>
      </div>
      <div className="row wrap" style={{ '--gap': '8px' }}>
        <input className="input" inputMode="tel" aria-label="Your phone number" value={phone} onChange={(e) => setPhone(e.target.value)} />
        {valid
          ? <CallButton garage={FRONT_DESK_GARAGE_NAME} getToken={async () => (await api('/api/call/start', { method: 'POST', anonymous: true, body: { garage_id: FRONT_DESK_GARAGE, phone } })).token} />
          : <button className="btn btn-primary" disabled>Call the garage</button>}
      </div>
    </div>
  )
}

function HowDiagram() {
  return (
    <figure className="card lp-diagram">
      <svg viewBox="0 0 760 300" role="img" aria-labelledby="how-title how-desc">
        <title id="how-title">How GarageCopilot works</title>
        <desc id="how-desc">The mechanic talks to the voice agent. The agent checks the vehicle manual, keeps the job card, and sends quotes to the customer's page for approval. The owner's floor updates live.</desc>
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0 10 5 0 10z" className="d-arrow" />
          </marker>
        </defs>
        <g className="d-node"><rect x="10" y="110" width="140" height="80" rx="16" /><text x="80" y="145">Mechanic</text><text x="80" y="168" className="d-small">headset, hands busy</text></g>
        <g className="d-node d-accent"><rect x="290" y="110" width="180" height="80" rx="16" /><text x="380" y="145">Voice agent</text><text x="380" y="168" className="d-small">Gemini Live + ADK</text></g>
        <g className="d-node"><rect x="610" y="20" width="140" height="80" rx="16" /><text x="680" y="55">Customer page</text><text x="680" y="78" className="d-small">on their phone</text></g>
        <g className="d-node"><rect x="610" y="200" width="140" height="80" rx="16" /><text x="680" y="235">Owner's floor</text><text x="680" y="258" className="d-small">live, in 3D</text></g>
        <g className="d-node d-soft"><rect x="300" y="10" width="160" height="56" rx="14" /><text x="380" y="43">Vehicle manual</text></g>
        <g className="d-node d-soft"><rect x="300" y="234" width="160" height="56" rx="14" /><text x="380" y="267">Job card · stock</text></g>
        <path d="M150 140 H285" className="d-line" markerEnd="url(#arrow)" /><path d="M285 160 H155" className="d-line" markerEnd="url(#arrow)" />
        <text x="218" y="130" className="d-small">talks</text><text x="218" y="182" className="d-small">answers</text>
        <path d="M380 108 V70" className="d-line d-dash" markerEnd="url(#arrow)" /><text x="392" y="94" className="d-small d-left">lookup, with page</text>
        <path d="M380 192 V230" className="d-line" markerEnd="url(#arrow)" />
        <path d="M472 130 C540 120 560 70 606 62" className="d-line" markerEnd="url(#arrow)" />
        <g className="d-badge"><rect x="486" y="120" width="96" height="26" rx="13" /><text x="534" y="138">Approve?</text></g>
        <path d="M606 82 C570 110 520 150 474 150" className="d-line d-ok" markerEnd="url(#arrow)" />
        <path d="M472 175 C540 190 560 230 606 238" className="d-line" markerEnd="url(#arrow)" />
        <text x="520" y="232" className="d-small">updates</text>
      </svg>
      {/* Phones: the same picture as a vertical flow, readable at 375 px */}
      <ol className="lp-flow-v" aria-label="How GarageCopilot works">
        <li><strong>Mechanic</strong><span>talks through the headset, hands busy</span></li>
        <li className="lp-v-accent"><strong>Voice agent</strong><span>Gemini Live + ADK: opens the job card, checks stock</span>
          <em>Vehicle manual: specs with the page</em></li>
        <li><strong>Customer page</strong><span>extra work waits for their OK</span><em className="lp-v-ok">Approve?</em></li>
        <li><strong>Owner's floor</strong><span>updates live, in 3D</span></li>
      </ol>
    </figure>
  )
}

// ---------------------------------------------------------------- pictures (inline SVG, theme colours)

function GreasyHands() {
  return (
    <svg viewBox="0 0 200 120">
      <rect x="20" y="70" width="70" height="40" rx="12" className="a-skin" />
      <rect x="28" y="62" width="14" height="22" rx="7" className="a-skin" /><rect x="44" y="58" width="14" height="26" rx="7" className="a-skin" />
      <rect x="60" y="60" width="14" height="24" rx="7" className="a-skin" />
      <circle cx="38" cy="92" r="6" className="a-grease" /><circle cx="62" cy="98" r="5" className="a-grease" /><circle cx="52" cy="80" r="4" className="a-grease" />
      <rect x="120" y="28" width="46" height="80" rx="10" className="a-phone" />
      <g className="a-ring"><path d="M112 34 q-10 12 0 24" /><path d="M174 34 q10 12 0 24" /><path d="M104 28 q-16 18 0 36" /><path d="M182 28 q16 18 0 36" /></g>
    </svg>
  )
}

function SurpriseBill() {
  return (
    <svg viewBox="0 0 200 120">
      <rect x="66" y="14" width="68" height="92" rx="8" className="a-paper" />
      <rect x="78" y="30" width="44" height="6" rx="3" className="a-ink" /><rect x="78" y="44" width="34" height="6" rx="3" className="a-ink" />
      <rect x="78" y="58" width="40" height="6" rx="3" className="a-ink" />
      <text x="100" y="92" className="a-big">₹ ?!</text>
      <circle cx="160" cy="36" r="16" className="a-skin" /><path d="M152 44 q8 -6 16 0" className="a-mouth" />
      <circle cx="155" cy="32" r="2" className="a-eye" /><circle cx="165" cy="32" r="2" className="a-eye" />
    </svg>
  )
}

function BlindOwner() {
  return (
    <svg viewBox="0 0 200 120">
      {[0, 1, 2].map((i) => <rect key={i} x={20 + i * 50} y="60" width="40" height="44" rx="8" className="a-bay" />)}
      <text x="40" y="88" className="a-q">?</text><text x="90" y="88" className="a-q">?</text><text x="140" y="88" className="a-q">?</text>
      <circle cx="170" cy="28" r="14" className="a-skin" /><path d="M160 22 h20" className="a-brow" />
    </svg>
  )
}

// ---------------------------------------------------------------- icons used by other screens too

export function MicIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 11a7 7 0 0 0 14 0M12 18v4" /></svg>
  )
}
export function GridIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><rect x="3" y="3" width="7" height="9" rx="2" /><rect x="14" y="3" width="7" height="5" rx="2" /><rect x="14" y="12" width="7" height="9" rx="2" /><rect x="3" y="16" width="7" height="5" rx="2" /></svg>
  )
}
export function PhoneIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="6" y="2" width="12" height="20" rx="3" /><path d="M11 18h2" /></svg>
  )
}
