// The voice session for a screen (mechanic or owner): status, transcript items and agent flags.
// Demo mode plays a script (src/demo/voice.js); otherwise src/voice/client.js talks to /ws/voice.
import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO } from '../config.js'
import { rupees, STAGE_LABEL } from '../format.js'

// role: 'mechanic' or 'owner' (picks the demo script; the real backend picks the agent from the token).
export function useVoice({ handsFree = false, role = 'mechanic' } = {}) {
  const [status, setStatus] = useState({ status: 'idle' })
  const [items, setItems] = useState([])
  const [flags, setFlags] = useState({ listening: false, speaking: false, thinking: false })
  const [currentJob, setCurrentJob] = useState(null)
  const voice = useRef(null)

  const onEvent = useCallback((e) => {
    switch (e.type) {
      case 'status': return setStatus(e)
      case 'listening':
      case 'speaking':
      case 'thinking': return setFlags((f) => ({ ...f, [e.type]: e.on }))
      case 'transcript':
        return setItems((list) => {
          const last = list[list.length - 1]
          if (last && last.kind === e.role && !last.final) return [...list.slice(0, -1), { ...last, text: e.text, final: e.final }]
          return [...list, { id: crypto.randomUUID?.() || Math.random(), kind: e.role, text: e.text, final: e.final }].slice(-40)
        })
      case 'tool': {
        const jobId = e.result?.job_id
        if (jobId) setCurrentJob(jobId)
        return setItems((list) => [...list, { id: Math.random(), kind: 'tool', text: toolText(e.name, e.result), final: true, error: !!e.result?.error }])
      }
      case 'notice': return setItems((list) => [...list, { id: Math.random(), kind: 'notice', text: e.text, final: true }])
      case 'note': return setItems((list) => [...list, { id: Math.random(), kind: 'note', text: e.text, final: true }])
      default:
    }
  }, [])

  // Never two live sessions for one screen (two Gemini sessions on one mic answer twice):
  // ignore a second tap while starting, and close any previous session before opening a new one.
  const starting = useRef(false)
  const start = useCallback(async () => {
    if (starting.current) return
    starting.current = true
    try {
      voice.current?.close()
      const mod = DEMO ? await import('../demo/voice.js') : await import('../voice/client.js')
      voice.current = DEMO ? mod.createDemoVoice({ onEvent, role }) : mod.createVoice({ onEvent, handsFree })
      await voice.current.connect()
    } finally {
      starting.current = false
    }
  }, [onEvent, handsFree, role])

  // Leaving the screen or the page (tab closed, Back, bfcache) ends the session and frees the mic.
  useEffect(() => {
    const stop = () => voice.current?.close()
    window.addEventListener('pagehide', stop)
    return () => { window.removeEventListener('pagehide', stop); stop() }
  }, [])
  return { status, items, flags, currentJob, setCurrentJob, voice, start, setItems }
}

export function toolText(name, r = {}) {
  if (r.error) return `${name.replaceAll('_', ' ')}: ${r.error}`
  switch (name) {
    case 'create_job': return `Job ${r.job_id} opened`
    case 'get_vehicle_history': return r.summary || 'History checked'
    case 'update_stage': return `${r.job_id} → ${STAGE_LABEL[r.stage] || r.stage}`
    case 'check_stock': return r.matches?.[0] ? `${r.matches[0].name}: ${r.matches[0].qty} in stock · ${rupees(r.matches[0].price)}` : 'Not in stock'
    case 'log_part_used': return `Stock updated · ${r.qty_left} left${r.low_stock ? ' (low)' : ''}`
    case 'close_job': return `${r.job_id} closed · ${rupees(r.bill)}`
    case 'describe_photo': return `Photo: “${r.caption}”`
    case 'quote_agent': return `Quote ${r.quote_id || ''} drafted${r.total ? ` · ${rupees(r.total)}` : ''}`
    case 'comms_agent': return r.status === 'pending' ? 'Sent to customer · waiting' : 'Message sent'
    case 'inventory_agent': return 'Owner asked about reorder'
    case 'today_summary': return `Today: ${r.open_jobs} open · ${rupees(r.revenue_today)}`
    case 'list_open_jobs': return `${r.count} open job${r.count === 1 ? '' : 's'}`
    case 'job_details': return `${r.job_id} · ${r.total_minutes} min`
    case 'pending_approvals': return `${r.count} waiting for customers`
    case 'low_stock': return `${r.low_stock?.length || 0} parts low`
    case 'recent_activity': return 'Activity checked'
    case 'lookup_manual': return r.found ? `Manual · ${r.source}` : 'Not in the manual'
    case 'answer_reorder': return r.status === 'ordered' ? `Ordered ${r.qty} from ${r.supplier}` : 'Reorder: ask again later'
    default: return name.replaceAll('_', ' ')
  }
}


// Space bar = push to talk on a laptop (not while typing in a text box).
export function useSpaceToTalk(voice, enabled) {
  useEffect(() => {
    if (!enabled) return
    const typingInField = (e) => /^(INPUT|TEXTAREA|SELECT)$/.test(e.target?.tagName || '')
    const down = (e) => { if (e.code === 'Space' && !e.repeat && !typingInField(e)) { e.preventDefault(); voice.current?.startTalking() } }
    const up = (e) => { if (e.code === 'Space' && !typingInField(e)) { e.preventDefault(); voice.current?.stopTalking() } }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    return () => { window.removeEventListener('keydown', down); window.removeEventListener('keyup', up) }
  }, [enabled, voice])
}
