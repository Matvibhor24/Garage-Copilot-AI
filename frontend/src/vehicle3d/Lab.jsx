// /preview/3d (dev and demo only): try the 3D views with any vehicle, stage and part.
// URL params work too: /preview/3d?vehicle=Activa&stage=service&part=Drive%20belt
import { useMemo, useState } from 'react'
import Vehicle3D from './Vehicle3D.jsx'
import { ZONE_LABELS } from './focus.js'

const STAGES = ['intake', 'service', 'waiting_approval', 'washing', 'done']

export default function Lab() {
  const q = new URLSearchParams(window.location.search)
  const [stage, setStage] = useState(q.get('stage') || 'service')
  const [part, setPart] = useState(q.get('part') || 'Clutch plate set')
  const only = q.get('vehicle')
  const az = q.get('az') != null ? Number(q.get('az')) : null

  const jobs = useMemo(() => {
    const make = (vehicle, plate) => ({
      vehicle, plate,
      stage: stage === 'waiting_approval' ? 'service' : stage,
      status: stage === 'done' ? 'done' : 'open',
      quotes: stage === 'waiting_approval' ? [{ status: 'pending', lines: [{ name: part }] }] : [],
      parts: stage === 'service' ? [{ name: part }] : [],
      complaint: stage === 'intake' ? part : '',
    })
    const all = [make('Splendor Plus', 'MH12AB1234'), make('Activa 6G', 'MH12CD5678')]
    return only ? all.filter((j) => j.vehicle.toLowerCase().includes(only.toLowerCase())) : all
  }, [stage, part, only])

  return (
    <main className="page stack" style={{ '--gap': '16px' }}>
      <h1>3D vehicle preview</h1>
      <div className="v3d-lab-controls">
        {STAGES.map((s) => (
          <button key={s} className={`btn btn-sm ${stage === s ? 'btn-primary' : ''}`} onClick={() => setStage(s)}>{s.replace('_', ' ')}</button>
        ))}
      </div>
      <div className="v3d-lab-controls">
        {Object.values(ZONE_LABELS).map((label) => (
          <button key={label} className={`btn btn-sm ${part === label ? 'btn-accent' : ''}`} onClick={() => setPart(label)}>{label}</button>
        ))}
      </div>
      <div className="v3d-lab">
        {jobs.map((j) => (
          <section key={j.vehicle} className="card stack" style={{ '--gap': '8px' }}>
            <h3>{j.vehicle}</h3>
            <Vehicle3D job={j} fixedAzimuth={az} />
          </section>
        ))}
      </div>
    </main>
  )
}
