// Owner: tap a job card to see the vehicle in 3D with what is happening to it right now.
import { useEffect, useRef, useState } from 'react'
import { api } from '../data/api.js'
import { minutes, plate, rupees } from '../format.js'
import Vehicle3D from './Vehicle3D.jsx'

export default function JobViewer({ job, quote, onClose }) {
  const dialog = useRef(null)
  const [full, setFull] = useState(null)

  useEffect(() => {
    dialog.current?.showModal()
    // The board has compact cards; the full job adds the parts fitted so far. Optional (demo mode has no endpoint).
    let stale = false
    api(`/api/owner/jobs/${job.id}`).then((j) => !stale && setFull(j)).catch(() => {})
    return () => { stale = true }
  }, [job.id])

  const view = { ...job, ...(full || {}), quotes: quote ? [quote] : [], parts: full?.parts || [] }
  const since = job.stage_started_at ? Math.max(0, Math.round((Date.now() - new Date(job.stage_started_at)) / 60000)) : null

  return (
    <dialog ref={dialog} className="v3d-dialog" onClose={onClose} onClick={(e) => e.target === dialog.current && dialog.current.close()}
      aria-labelledby="job-viewer-title">
      <div className="v3d-dialog-body">
        <div className="row between">
          <div className="stack" style={{ '--gap': '2px' }}>
            <span className="muted small mono">{job.id}</span>
            <h2 id="job-viewer-title">{job.vehicle} · {plate(job.plate)}</h2>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => dialog.current.close()} autoFocus>Close</button>
        </div>
        <Vehicle3D job={view} compact />
        <div className="v3d-facts">
          <div><span className="muted small">Customer</span><strong>{job.owner}</strong></div>
          <div><span className="muted small">Mechanic</span><strong>{job.mechanic_name || '—'}</strong></div>
          <div><span className="muted small">In this stage</span><strong>{since == null ? '—' : minutes(since)}</strong></div>
          <div><span className="muted small">{job.status === 'done' ? 'Final bill' : 'Bill so far'}</span><strong>{rupees(view.bill || 0)}</strong></div>
        </div>
        {job.complaint && <p className="muted small">Complaint: {job.complaint}</p>}
      </div>
    </dialog>
  )
}
