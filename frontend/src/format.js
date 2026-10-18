// Small display helpers shared by every screen.

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function rupees(n) {
  return `₹${inr.format(Math.round(n || 0))}`
}

export function clock(iso) {
  if (!iso) return ''
  // Garages are in India: always show IST, whatever the viewer's device says.
  return new Date(iso).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' })
}

export function minutes(n) {
  if (n == null) return ''
  if (n < 60) return `${n} min`
  const h = Math.floor(n / 60)
  const m = n % 60
  return m ? `${h} h ${m} min` : `${h} h`
}

export function ago(iso, now = Date.now()) {
  if (!iso) return ''
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000))
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  return `${Math.round(s / 86400)} d ago`
}

export function plate(p) {
  // MH12AB1234 -> MH 12 AB 1234
  const m = /^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$/.exec(p || '')
  return m ? [m[1], m[2], m[3], m[4]].filter(Boolean).join(' ') : p || ''
}

export const STAGE_LABEL = {
  intake: 'Checked in',
  service: 'In service',
  waiting_approval: 'Waiting for approval',
  washing: 'Washing',
  ready: 'Ready for pickup',
  done: 'Ready for pickup',
}

const ACTION_LABEL = {
  create_job: 'opened a job',
  get_vehicle_history: 'checked vehicle history',
  update_stage: 'moved a job',
  check_stock: 'checked stock',
  log_part_used: 'used a part',
  close_job: 'closed a job',
  add_photo: 'added a photo',
  describe_photo: 'captioned a photo',
  draft_quote: 'drafted a quote',
  send_quote: 'sent a quote',
  quote_approved: 'approved a quote',
  quote_rejected: 'rejected a quote',
  send_status_link: 'sent a status link',
  ask_reorder: 'asked to reorder',
  reorder: 'reordered stock',
  reorder_later: 'put a reorder off',
  restock: 'restocked',
  invite_mechanic: 'invited a mechanic',
  approval_nudge: 'nudged an approval',
  lookup_manual: 'looked up the manual',
  update_settings: 'changed settings',
  web_search_fixes: 'searched the web',
  caller_status: 'told a caller their status',
  caller_wait_time: 'told a caller the wait',
  topic_blocked: 'blocked an off-topic request',
  armor_flagged: 'AI safety: flagged by Model Armor',
  resend_quote: 'sent a quote again',
  request_estimate: 'asked for a price',
  answer_estimate: 'answered a price request',
  book_dropoff: 'booked a drop-off',
  request_callback: 'asked for a callback',
  close_callback: 'called back',
}

export function actionLabel(a) {
  return ACTION_LABEL[a] || a.replaceAll('_', ' ')
}

// One line of detail for an audit entry, from the stored tool result.
export function actionDetail(entry) {
  const d = entry.details || {}
  switch (entry.action) {
    case 'create_job': return `${d.job_id} · ${plate(d.plate)} · ${d.owner}`
    case 'update_stage': return `${d.job_id} → ${STAGE_LABEL[d.stage] || d.stage}`
    case 'check_stock': return d.matches?.[0] ? `${d.matches[0].name}: ${d.matches[0].qty} left, ${rupees(d.matches[0].price)}` : d.query
    case 'log_part_used': return `${d.name} × ${d.qty_used} on ${d.job_id}`
    case 'close_job': return `${d.job_id} · bill ${rupees(d.bill)}`
    case 'send_quote':
      if (d.auto) return `${d.quote_id} · ${rupees(d.total)} · approved automatically (within the ${rupees(d.quote_limit)} limit)`
    // falls through
    case 'draft_quote':
    case 'quote_approved':
    case 'quote_rejected': return [d.quote_id, d.total != null ? rupees(d.total) : '', d.reason || ''].filter(Boolean).join(' · ')
    case 'ask_reorder': return d.text || d.part_id
    case 'reorder': return `${d.qty} × ${d.name} from ${d.supplier}`
    case 'restock': return `${d.part_id} → ${d.qty}`
    case 'get_vehicle_history': return d.summary || d.plate
    case 'describe_photo': return d.caption ? `“${d.caption}”` : ''
    case 'request_estimate': return `${d.estimate_id} · ${d.status}`
    case 'answer_estimate': return `${d.estimate_id} · ${d.status}${d.total != null ? ` · ${rupees(d.total)}` : ''}`
    case 'book_dropoff': return `${d.booking_id} · ${d.when}`
    case 'request_callback': return d.callback_id || ''
    case 'armor_flagged': return [d.where, (d.reasons || []).join(', '), d.action].filter(Boolean).join(' · ')
    case 'topic_blocked': return d.text ? `“${d.text}” (${d.where})` : d.where || ''
    case 'caller_wait_time': return `${d.vehicles_ahead} ahead · starts in ~${d.start_in_minutes?.[0]}–${d.start_in_minutes?.[1]} min`
    case 'web_search_fixes': return `${d.question} (web${d.sites?.length ? ` · ${d.sites.join(', ')}` : ': nothing found'})`
    case 'update_settings': return d.summary ? d.summary.replace(/^changed /, '') : ''
    case 'lookup_manual': return `${d.question} (${d.found ? d.source : `${d.vehicle}: not in the manual`})`
    default: return d.job_id || ''
  }
}
