// The customer's (and owner's) live 3D view of the vehicle: the part being worked on glows, the stage
// plays as an effect (foam and water while washing, sparks during service, sparkles when ready).
// three.js is loaded only when this view is on screen; phones without WebGL simply don't show it.
import { useEffect, useMemo, useRef, useState } from 'react'
import { scene as describe } from './focus.js'
import './vehicle3d.css'

function webglOk() {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

/**
 * job: { vehicle, plate, stage, status, quotes?, parts?, complaint? } (customer view or an owner job)
 * compact: smaller frame (owner modal on phones)
 */
export default function Vehicle3D({ job, compact = false, caption = true, className = '', fixedAzimuth = null }) {
  const s = useMemo(() => describe(job), [job])
  const box = useRef(null)
  const canvas = useRef(null)
  const label = useRef(null)
  const api = useRef(null)
  const [state, setState] = useState('loading') // loading | ready | off
  const supported = useMemo(() => !!s.kind && webglOk(), [s.kind])

  // Build the scene once per vehicle (kind + plate); stage changes only update it.
  useEffect(() => {
    if (!supported) return
    let cancelled = false
    let stopObservers = () => {}
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    import('./scene3d.js').then(({ createScene }) => {
      if (cancelled || !canvas.current) return
      const placeLabel = () => {
        const el = label.current
        const at = api.current?.anchorOnScreen()
        if (!el) return
        if (!at || !at.visible) { el.style.opacity = '0'; return }
        el.style.opacity = '1'
        el.style.transform = `translate(${Math.round(at.x)}px, ${Math.round(at.y)}px)`
      }
      api.current = createScene(canvas.current, { kind: s.kind, plate: job.plate, reducedMotion, onFrame: placeLabel, fixedAzimuth })
      const size = () => {
        const r = box.current.getBoundingClientRect()
        if (r.width && r.height) api.current.resize(r.width, r.height)
      }
      size()
      const ro = new ResizeObserver(size)
      ro.observe(box.current)
      // Stop drawing when scrolled away or the tab is hidden: saves battery on phones.
      let onScreen = true
      const sync = () => api.current?.setActive(onScreen && document.visibilityState === 'visible')
      const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; sync() })
      io.observe(box.current)
      document.addEventListener('visibilitychange', sync)
      stopObservers = () => { ro.disconnect(); io.disconnect(); document.removeEventListener('visibilitychange', sync) }
      setState('ready')
    }).catch(() => setState('off'))
    return () => {
      cancelled = true
      stopObservers()
      api.current?.dispose()
      api.current = null
    }
  }, [supported, s.kind, job.plate])

  useEffect(() => {
    if (state === 'ready') api.current?.setState({ stage: s.stage, zones: s.zones, focus: s.focus })
  }, [state, s.stage, s.focus, s.zones.join()])

  if (!supported || state === 'off') return null

  const tone = s.stage === 'waiting_approval' ? 'warn' : s.stage === 'done' ? 'ok' : s.stage === 'washing' ? 'wash' : 'accent'
  const partLabel = s.focus && s.stage !== 'washing' && s.stage !== 'done' ? (s.detail.split(': ')[1] || '') : ''
  return (
    <figure className={`v3d ${compact ? 'v3d-compact' : ''} v3d-${tone} ${className}`} aria-label={`${job.vehicle}: ${s.title}. ${s.detail}`}>
      <div className="v3d-stage" ref={box}>
        <canvas ref={canvas} />
        {state === 'loading' && <div className="v3d-loading"><span className="spinner" /></div>}
        <div className="v3d-label" ref={label} aria-hidden="true" style={{ opacity: 0 }}>
          {partLabel && <span>{partLabel.length > 28 ? `${partLabel.slice(0, 26)}…` : partLabel}</span>}
        </div>
        <span className="v3d-hint" aria-hidden="true">Drag to turn</span>
      </div>
      {caption && (
        <figcaption className="v3d-caption">
          <span className="v3d-dot" aria-hidden="true" />
          <strong>{s.title}</strong>
          {s.detail && <span className="muted">· {s.detail}</span>}
        </figcaption>
      )}
    </figure>
  )
}
