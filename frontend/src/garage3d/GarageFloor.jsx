// Owner > Floor: the whole garage in 3D, live. Every open job is a vehicle at its station (front door, a service
// lift, the wash bay, delivery); mechanics stand by the vehicle they're working on; a vehicle waiting for the
// customer's OK pulses on its lift. Click a vehicle to inspect the job; "Open in 3D" shows the part being worked on.
import { useEffect, useMemo, useRef, useState } from 'react'
import { minutes, plate, rupees } from '../format.js'
import JobViewer from '../vehicle3d/JobViewer.jsx'
import { layout, STATIONS } from './layout.js'
import './garage3d.css'

function webglOk() {
  try {
    const c = document.createElement('canvas')
    return !!(c.getContext('webgl2') || c.getContext('webgl'))
  } catch {
    return false
  }
}

const STATION_OF = { door: 'Front door', wash: 'Wash bay', service: 'Service bay', delivery: 'Delivery', delivered: 'Delivered' }
const since = (iso) => (iso ? Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000)) : null)

export default function GarageFloor({ dash }) {
  const plan = useMemo(() => layout(dash), [dash])
  const box = useRef(null)
  const canvas = useRef(null)
  const api = useRef(null)
  const labelEls = useRef({})
  const [state, setState] = useState('loading') // loading | ready | off
  const [selected, setSelected] = useState(null)
  const [viewing, setViewing] = useState(null)
  const [layers, setLayers] = useState({ plates: true, names: true })
  const supported = useMemo(() => webglOk(), [])
  const low = dash.low_stock.length > 0

  useEffect(() => {
    if (!supported) return
    let cancelled = false
    let stop = () => {}
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    import('./garageScene.js').then(({ createGarage }) => {
      if (cancelled || !canvas.current) return
      const place = () => {
        const seen = new Set()
        for (const l of api.current?.labels() || []) {
          const el = labelEls.current[l.key]
          if (!el) continue
          seen.add(l.key)
          el.style.transform = `translate(${Math.round(l.x)}px, ${Math.round(l.y)}px)`
          el.style.opacity = '1'
        }
        for (const [key, el] of Object.entries(labelEls.current)) if (el && !seen.has(key)) el.style.opacity = '0'
      }
      api.current = createGarage(canvas.current, { onSelect: (id) => id && setSelected(id), onFrame: place, reducedMotion })
      if (import.meta.env.DEV) window.__garage = api.current
      const size = () => {
        const r = box.current.getBoundingClientRect()
        if (r.width && r.height) api.current.resize(r.width, r.height)
      }
      size()
      const ro = new ResizeObserver(size)
      ro.observe(box.current)
      let onScreen = true
      const sync = () => api.current?.setActive(onScreen && document.visibilityState === 'visible')
      const io = new IntersectionObserver(([e]) => { onScreen = e.isIntersecting; sync() })
      io.observe(box.current)
      document.addEventListener('visibilitychange', sync)
      stop = () => { ro.disconnect(); io.disconnect(); document.removeEventListener('visibilitychange', sync) }
      setState('ready')
    }).catch(() => setState('off'))
    return () => {
      cancelled = true
      stop()
      api.current?.dispose()
      api.current = null
    }
  }, [supported])

  useEffect(() => {
    if (state === 'ready') api.current?.update(plan, { low })
  }, [state, plan, low])

  useEffect(() => {
    api.current?.select(selected)
  }, [state, selected])

  const pendingFor = Object.fromEntries(dash.pending_approvals.map((q) => [q.job_id, q]))
  const job = dash.jobs.find((j) => j.id === selected) || null
  const placed = plan.vehicles.find((v) => v.id === selected)
  const alerts = [
    ...dash.pending_approvals.map((q) => ({ key: q.id, tag: 'WAIT', tone: 'crit', title: `${q.id} · ${rupees(q.total)}`,
      sub: `Waiting on ${dash.jobs.find((j) => j.id === q.job_id)?.owner || 'customer'}`, at: q.sent_at, job: q.job_id })),
    ...dash.low_stock.map((p) => ({ key: p.part_id, tag: 'STOCK', tone: 'warn', title: p.name, sub: `${p.qty} left` })),
    ...(plan.overflow ? [{ key: 'overflow', tag: 'FLOOR', tone: 'warn', title: `${plan.overflow} waiting for a lift`, sub: 'All bays busy' }] : []),
    ...dash.messages.slice(0, 4).map((m) => ({ key: m.id || m.at, tag: 'INFO', tone: 'info', title: m.text, at: m.at })),
  ]
  const flow = [
    ['At door', plan.counts.door], ['In bays', plan.counts.service], ['Need OK', plan.counts.waiting],
    ['Washing', plan.counts.wash], ['Ready', plan.counts.delivery], ['Delivered', plan.counts.delivered],
  ]

  return (
    <div className="gf enter">
      <aside className="gf-rail gf-panel">
        <div className="gf-rail-head">
          <span className="gf-title">[FLOOR]</span>
          <span className="gf-live" aria-hidden="true" />
        </div>
        <nav className="gf-stations" aria-label="Stations">
          {STATIONS.map((s) => (
            <button key={s.key} onClick={() => api.current?.focus(s.key)}>
              <span>{s.label}</span>
              <span className="mono">{plan.counts[s.key]}</span>
            </button>
          ))}
        </nav>
        <div className="gf-rule" />
        <span className="gf-label">Layers</span>
        <label className="gf-check"><input type="checkbox" checked={layers.plates} onChange={(e) => setLayers({ ...layers, plates: e.target.checked })} /> Vehicles</label>
        <label className="gf-check"><input type="checkbox" checked={layers.names} onChange={(e) => setLayers({ ...layers, names: e.target.checked })} /> Mechanics</label>
        <div className="gf-rule" />
        <span className="gf-label">Crew</span>
        <ul className="gf-crew">
          {plan.mechanics.map((m) => (
            <li key={m.name}><button onClick={() => setSelected(m.jobId)}><span className="gf-dot" />{m.name}<span className="muted mono small">{m.jobId}</span></button></li>
          ))}
          {!plan.mechanics.length && <li className="muted small">Nobody on a vehicle</li>}
        </ul>
      </aside>

      <section className="gf-stage gf-panel" ref={box} aria-label="3D garage floor">
        {supported ? <canvas ref={canvas} /> : <div className="gf-fallback muted">3D needs WebGL. The Today board shows the same jobs.</div>}
        {state === 'loading' && supported && <div className="gf-loading"><span className="spinner" /></div>}
        <span className="gf-corner tl" /><span className="gf-corner tr" /><span className="gf-corner bl" /><span className="gf-corner br" />
        <div className="gf-labels" aria-hidden="true">
          {layers.plates && plan.vehicles.map((v) => (
            <span key={v.id} ref={(el) => { labelEls.current[v.id] = el }}
              className={`gf-tag ${v.alert ? 'gf-tag-warn' : ''} ${v.id === selected ? 'gf-tag-on' : ''}`}>
              <b>{v.id}</b> <span className="gf-tag-model">{v.vehicle}</span>
            </span>
          ))}
          {layers.names && plan.mechanics.map((m) => (
            <span key={m.name} ref={(el) => { labelEls.current[m.name] = el }} className="gf-name">{m.name}</span>
          ))}
        </div>
        <span className="gf-hint">Drag to look around · click a vehicle</span>
      </section>

      <section className="gf-inspector gf-panel">
        <span className="gf-label">Job inspector</span>
        {job ? (
          <>
            <div className="gf-inspect-head">
              <strong>{job.vehicle}</strong>
              <span className="mono muted">{job.id}</span>
            </div>
            <dl className="gf-facts">
              <div><dt>Plate</dt><dd className="mono">{plate(job.plate)}</dd></div>
              <div><dt>Customer</dt><dd>{job.owner}</dd></div>
              <div><dt>Mechanic</dt><dd>{job.mechanic_name || '—'}</dd></div>
              <div><dt>Where</dt><dd>{STATION_OF[placed?.station || (job.status === 'done' ? 'delivered' : '')] || '—'}{placed?.station === 'service' && placed.slot < 3 ? ` ${placed.slot + 1}` : ''}</dd></div>
              <div><dt>In stage</dt><dd className="mono">{since(job.stage_started_at) == null ? '—' : minutes(since(job.stage_started_at))}</dd></div>
              <div><dt>{job.status === 'done' ? 'Bill' : 'Bill so far'}</dt><dd className="mono">{rupees(job.bill || 0)}</dd></div>
              {pendingFor[job.id] && <div className="gf-wide"><dt>Quote</dt><dd className="gf-warn">{pendingFor[job.id].id} · {rupees(pendingFor[job.id].total)} · waiting for OK</dd></div>}
            </dl>
            <button className="btn btn-sm btn-accent" onClick={() => setViewing(job)}>Open in 3D</button>
          </>
        ) : <p className="muted small">Click a vehicle or a mechanic on the floor.</p>}
      </section>

      <section className="gf-flow gf-panel">
        <span className="gf-label">Floor flow · today</span>
        <div className="gf-numbers">
          {flow.map(([label, n]) => (
            <div key={label} className={label === 'Need OK' && n ? 'gf-hot' : ''}>
              <span className="gf-big mono">{n}</span>
              <span className="gf-small">{label}</span>
            </div>
          ))}
        </div>
        <div className="gf-bar" aria-hidden="true">
          {plan.vehicles.map((v) => <span key={v.id} className={`gf-seg gf-seg-${v.station} ${v.alert ? 'gf-seg-warn' : ''}`} title={`${v.id} ${v.vehicle}`} />)}
          {Array.from({ length: plan.counts.delivered }, (_, i) => <span key={`d${i}`} className="gf-seg gf-seg-delivered" />)}
        </div>
      </section>

      <section className="gf-alerts gf-panel">
        <div className="row between"><span className="gf-label">Alert feed</span><span className="mono small muted">{alerts.filter((a) => a.tone !== 'info').length} active</span></div>
        <ul>
          {alerts.map((a) => (
            <li key={a.key} className={`gf-alert gf-alert-${a.tone}`} onClick={() => a.job && setSelected(a.job)}>
              <span className="mono small muted">{a.at ? new Date(a.at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }) : '··:··'}</span>
              <span className="gf-alert-text"><b>{a.title}</b>{a.sub && <span className="muted small"> {a.sub}</span>}</span>
              <span className="gf-chip">{a.tag}</span>
            </li>
          ))}
          {!alerts.length && <li className="muted small">All quiet.</li>}
        </ul>
      </section>

      {viewing && <JobViewer job={viewing} quote={pendingFor[viewing.id]} onClose={() => setViewing(null)} />}
    </div>
  )
}
