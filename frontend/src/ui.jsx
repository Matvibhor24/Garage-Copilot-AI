// Shared UI pieces. Plain components, plain CSS classes from styles.css.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

export function Brand({ live = false, to = '/' }) {
  return (
    <Link to={to} className={`brand ${live ? 'brand-live' : ''}`} aria-label="GarageCopilot home" viewTransition>
      <span className="brand-mark">
        <span className="brand-bars"><span /><span /><span /><span /></span>
      </span>
      <span>GarageCopilot</span>
    </Link>
  )
}

export function LiveBadge({ label = 'Live' }) {
  return (
    <span className="chip chip-ok"><span className="dot live-dot" />{label}</span>
  )
}

export function Skeleton({ h = 20, w = '100%', style }) {
  return <div className="skeleton" style={{ height: h, width: w, ...style }} />
}

// Animated number: eases from the previous value to the new one.
export function CountUp({ value, format = (n) => String(n), ms = 700 }) {
  const [shown, setShown] = useState(value || 0)
  const from = useRef(value || 0)
  useEffect(() => {
    const start = performance.now()
    const a = from.current
    const b = value || 0
    if (a === b || window.matchMedia?.('(prefers-reduced-motion: reduce)').matches) {
      setShown(b)
      from.current = b
      return
    }
    let raf
    const tick = (t) => {
      const k = Math.min(1, (t - start) / ms)
      const eased = 1 - Math.pow(1 - k, 3)
      setShown(a + (b - a) * eased)
      if (k < 1) raf = requestAnimationFrame(tick)
      else from.current = b
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [value, ms])
  return <span className="num">{format(Math.round(shown))}</span>
}

// Check mark that draws itself.
export function Check({ size = 56, color = 'var(--ok)' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 56 56" aria-hidden="true">
      <circle cx="28" cy="28" r="26" fill="none" stroke={color} strokeWidth="3" strokeDasharray="164" strokeDashoffset="164"
        style={{ animation: 'draw 600ms var(--ease) forwards' }} />
      <path d="M17 29 l7 7 l15 -16" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round"
        strokeDasharray="40" strokeDashoffset="40" style={{ animation: 'draw 420ms 380ms var(--ease) forwards' }} />
    </svg>
  )
}

export function Spinner() {
  return <span className="spinner" aria-label="Loading" />
}

export function ErrorNote({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="card card-flat row between fade" role="alert" style={{ borderColor: 'var(--bad-soft)' }}>
      <span className="small">{error.message || String(error)}</span>
      {onRetry && <button className="btn btn-sm" onClick={onRetry}>Try again</button>}
    </div>
  )
}

const ToastContext = createContext(() => {})

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const push = useCallback((text) => {
    const id = Math.random().toString(36).slice(2)
    setToasts((t) => [...t, { id, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 3200)
  }, [])
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="toasts" aria-live="polite">
        {toasts.map((t) => <div key={t.id} className="toast">{t.text}</div>)}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  return useContext(ToastContext)
}
