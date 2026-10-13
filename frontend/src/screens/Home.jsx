import { Link } from 'react-router-dom'
import { Brand } from '../ui.jsx'
import { DEMO } from '../config.js'

function RoleCard({ to, title, text, icon, i }) {
  return (
    <Link to={to} className="card role-card enter" style={{ '--i': i }} viewTransition>
      <span className="role-icon" aria-hidden="true">{icon}</span>
      <span className="stack" style={{ '--gap': '4px' }}>
        <h2>{title}</h2>
        <span className="muted small">{text}</span>
      </span>
      <span className="role-arrow" aria-hidden="true">→</span>
    </Link>
  )
}

export default function Home() {
  return (
    <main className="page home">
      <header className="topbar">
        <Brand live />
        {DEMO && <span className="chip chip-accent">Demo mode</span>}
      </header>

      <section className="home-hero enter">
        <div className="wave" aria-hidden="true">
          {Array.from({ length: 24 }, (_, i) => <span key={i} style={{ '--i': i }} />)}
        </div>
        <h1>Hands on the bike.<br /><span className="muted">Paperwork on autopilot.</span></h1>
        <p className="muted">Talk through your headset. Job cards, stock, quotes and customer approvals happen on their own.</p>
      </section>

      <nav className="role-grid" aria-label="Choose your screen">
        <RoleCard i={1} to="/mechanic" title="I'm a mechanic" text="Voice copilot for the headset" icon={<MicIcon />} />
        <RoleCard i={2} to="/owner" title="I run the garage" text="Live jobs, approvals, stock and the day's money" icon={<GridIcon />} />
        {DEMO && <RoleCard i={3} to="/j/demo-J-1042" title="See what the customer sees" text="Ramesh's status page, job J‑1042" icon={<PhoneIcon />} />}
      </nav>
    </main>
  )
}

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
