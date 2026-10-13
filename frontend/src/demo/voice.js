// Demo voice: plays the six-step demo job from diagrams/job-workflow.png instead of talking to Gemini
// (and, for the owner, a few questions about the day answered from the demo data).
// Same event interface as the real voice client (src/voice/client.js), so the screens
// cannot tell the difference. Each push-to-talk (or typed message) plays the next line.
import { minutes, rupees, STAGE_LABEL } from '../format.js'
import { dashboard, ownerStock } from './server.js'
import * as store from './store.js'
import { at, billOf, GARAGE, moveStage } from './store.js'

const SCRIPT = [
  {
    say: 'New bike, Splendor Plus, MH12 AB 1234, owner Ramesh, clutch slipping, general service.',
    time: '10:02',
    run(s) {
      const j = store.createJob(s, 'MH12AB1234', 'Splendor Plus', 'Ramesh', 'clutch slipping, general service')
      s.current = j.id
      store.audit(s, 'get_vehicle_history', { plate: j.plate, summary: 'Last visit 8 months ago: clutch hard, service (Clutch cable).' })
      return {
        tools: [['create_job', { job_id: j.id, plate: j.plate, owner: 'Ramesh', stage: 'intake' }],
          ['get_vehicle_history', { summary: 'Last clutch work 8 months ago' }]],
        reply: `Job ${j.id} open for Ramesh's Splendor. Last clutch work was 8 months ago. Status link sent to Ramesh.`,
      }
    },
  },
  {
    say: 'Moving it to washing.',
    time: '10:23',
    run(s) {
      moveStage(s, s.jobs[s.current], 'washing')
      store.audit(s, 'update_stage', { job_id: s.current, stage: 'washing' })
      return { tools: [['update_stage', { job_id: s.current, stage: 'washing' }]], reply: 'Washing. Got it.' }
    },
  },
  {
    say: 'Started service.',
    time: '10:41',
    run(s) {
      const mins = moveStage(s, s.jobs[s.current], 'service')
      store.audit(s, 'update_stage', { job_id: s.current, stage: 'service', previous_minutes: mins })
      return { tools: [['update_stage', { job_id: s.current, stage: 'service' }]], reply: `In service. Washing took ${mins} minutes.` }
    },
  },
  {
    say: 'Do we have a clutch plate for Splendor? Price?',
    time: '10:52',
    run(s) {
      const p = s.inventory['clutch-splendor']
      const match = { part_id: p.id, name: p.name, qty: p.qty, price: p.price, labour: p.labour }
      store.audit(s, 'check_stock', { query: 'clutch plate', matches: [match] })
      const n = ['None', 'One', 'Two', 'Three', 'Four', 'Five'][p.qty] || p.qty
      return { tools: [['check_stock', { matches: [match] }]], reply: `${n} in stock, ${rupees(p.price)}, labour ${rupees(p.labour)}.` }
    },
  },
  {
    say: 'Show Ramesh the worn plate.',
    note: 'Phone camera snaps a photo',
    time: '10:58',
    run(s) {
      const j = s.jobs[s.current]
      const p = s.inventory['clutch-splendor']
      const id = `Q-${s.next_quote_no++}`
      const total = p.price + p.labour
      const lines = [{ part_id: p.id, name: p.name, qty: 1, price: p.price, total: p.price }]
      s.quotes[id] = {
        job_id: j.id, customer_id: j.customer_id, lines, labour: p.labour, total, quote_limit: GARAGE.quote_limit,
        lang: 'mr', note: 'clutch plate worn', photo: `photos/${GARAGE.id}/${j.id}/demo.jpg`, photo_caption: 'friction surface glazed',
        status: 'pending', created_at: s.now, sent_at: s.now,
        text: `नमस्कार Ramesh, तुमच्या Splendor Plus साठी अंदाज:\nClutch plate set x1: ₹650\nमजुरी: ₹300\nएकूण: ₹950\nफोटो: friction surface glazed`,
      }
      j.pending_quote = id
      store.audit(s, 'add_photo', { job_id: j.id })
      store.audit(s, 'describe_photo', { job_id: j.id, caption: 'friction surface glazed' })
      store.audit(s, 'draft_quote', { quote_id: id, total })
      store.audit(s, 'send_quote', { quote_id: id, total, reason: `₹${total} > ₹${GARAGE.quote_limit} limit` })
      store.notify(s, j.customer_id, 'quote', s.quotes[id].text, { job_id: j.id, quote_id: id })
      return {
        tools: [['describe_photo', { caption: 'friction surface glazed' }], ['quote_agent', { quote_id: id, total }], ['comms_agent', { quote_id: id, status: 'pending' }]],
        reply: `Quote ${id} for ${rupees(total)} sent to Ramesh in Marathi. It's over your ${rupees(GARAGE.quote_limit)} limit, so I'll tell you when he answers.`,
        waitFor: id,
      }
    },
  },
  {
    say: 'Used one clutch plate set.',
    time: '11:40',
    run(s) {
      const j = s.jobs[s.current]
      const p = s.inventory['clutch-splendor']
      p.qty -= 1
      p.low_stock = p.qty <= p.low_at
      j.parts.push({ part_id: p.id, name: p.name, qty: 1, price: p.price, total: p.price })
      j.bill = billOf(j)
      store.audit(s, 'log_part_used', { job_id: j.id, name: p.name, qty_used: 1, qty_left: p.qty })
      const text = `${p.name} down to ${p.qty}. Reorder 5 from ${GARAGE.supplier}?`
      s.reorder_asks[p.id] = { part_id: p.id, name: p.name, qty_left: p.qty, reorder_qty: 5, supplier: GARAGE.supplier, text, status: 'asked', at: s.now }
      store.audit(s, 'ask_reorder', { part_id: p.id, text })
      store.notify(s, 'owner', 'reorder_ask', text, { part_id: p.id })
      return {
        tools: [['log_part_used', { qty_left: p.qty, low_stock: true }], ['inventory_agent', { asked_owner: true }]],
        reply: `Logged one clutch plate set. Only ${p.qty} left, so I've asked Asha about reordering.`,
      }
    },
  },
  {
    say: 'Job done.',
    time: '11:41',
    run(s) {
      const j = s.jobs[s.current]
      moveStage(s, j, 'done')
      j.status = 'done'
      j.closed_at = s.now
      j.bill = billOf(j)
      store.audit(s, 'close_job', { job_id: j.id, bill: j.bill })
      store.notify(s, j.customer_id, 'final_bill', `नमस्कार Ramesh, तुमची Splendor Plus तयार आहे. अंतिम बिल: ₹${j.bill}.`, { job_id: j.id })
      s.current = null
      return { tools: [['close_job', { job_id: j.id, bill: j.bill }]], reply: `Closed ${j.id}. Final bill ${rupees(j.bill)}, sent to Ramesh.` }
    },
  },
  {
    // Manual lookup (C08). The demo has no real manual: the answer and the source are made up and say so.
    say: "What's the clutch lever free play on the Splendor?",
    time: '11:45',
    run(s) {
      const source = "Demo manual p.12"
      const result = {
        found: true, vehicle: 'Splendor Plus', source,
        answer_sources: [{ title: 'Demo manual (made-up text, not a real spec)', page: 12, section: 'Clutch', text: 'Demo text: clutch lever free play 2 to 3 cm at the lever tip.' }],
      }
      store.audit(s, 'lookup_manual', { question: 'clutch lever free play', vehicle: 'Splendor Plus', found: true, source })
      return { tools: [['lookup_manual', result]], reply: 'Demo answer, not a real spec: 2 to 3 centimetres at the lever tip. Demo manual, page 12.' }
    },
  },
]

// The owner asks about the day. Answers are worked out from the demo data at the moment they are asked,
// so they follow whatever the mechanic tab has done. The list repeats.
const OWNER_SCRIPT = [
  {
    say: 'How many bikes are in today?',
    run(s) {
      const d = dashboard(s)
      const closed = Object.keys(d.minutes_per_job).length
      const busiest = Object.entries(d.jobs_by_stage).sort((a, b) => b[1] - a[1])[0]
      return {
        tools: [['today_summary', { open_jobs: d.open_jobs, revenue_today: d.revenue_today }]],
        reply: `${d.open_jobs} open jobs right now, most of them ${STAGE_LABEL[busiest[0]].toLowerCase()}. ${closed} closed today.`,
      }
    },
  },
  {
    say: "What's pending approval?",
    run(s) {
      const pending = dashboard(s).pending_approvals
      const q = pending[0]
      return {
        tools: [['pending_approvals', { count: pending.length }]],
        reply: q ? `Quote ${q.id} for ${rupees(q.total)} on ${q.job_id}, waiting for ${s.jobs[q.job_id].owner}.` : 'Nothing is waiting for a customer right now.',
      }
    },
  },
  {
    say: 'How much did we make today?',
    run(s) {
      const d = dashboard(s)
      const n = Object.keys(d.minutes_per_job).length
      return {
        tools: [['today_summary', { open_jobs: d.open_jobs, revenue_today: d.revenue_today }]],
        reply: `${rupees(d.revenue_today)} from ${n} closed job${n === 1 ? '' : 's'} today.`,
      }
    },
  },
  {
    say: 'Which parts are low?',
    run(s) {
      const low = Object.values(s.inventory).filter((p) => p.low_stock)
      return {
        tools: [['low_stock', { low_stock: low }]],
        reply: low.length ? low.map((p) => `${p.name} for ${p.fits[0]}: ${p.qty} left`).join('. ') + '.' : 'Nothing is low. Stock looks fine.',
      }
    },
  },
  {
    say: "How long did Ramesh's job take?",
    run(s) {
      const j = Object.values(s.jobs).find((x) => x.owner === 'Ramesh')
      if (!j) return { tools: [['job_details', { error: 'no job for Ramesh today' }]], reply: "Ramesh's bike hasn't come in yet." }
      const done = Object.values(j.stage_minutes).reduce((a, b) => a + b, 0)
      const total = j.status === 'done' ? done : done + Math.round((new Date(s.now) - new Date(j.stage_started_at)) / 60000)
      return {
        tools: [['job_details', { job_id: j.id, total_minutes: total }]],
        reply: j.status === 'done' ? `${j.id} took ${minutes(total)} from check-in to ready.` : `${j.id} has been in for ${minutes(total)} so far, now ${STAGE_LABEL[j.stage].toLowerCase()}.`,
      }
    },
  },
  {
    say: 'Yes, reorder the clutch plates.',
    run(s) {
      const ask = Object.values(s.reorder_asks).find((a) => a.status === 'asked')
      if (!ask) return { tools: [], reply: "There's no reorder question open right now." }
      const out = ownerStock(ask.part_id, 'reorder', {})
      return { tools: [['answer_reorder', out]], reply: `Done. Ordered ${out.qty} ${out.name.toLowerCase()} from ${out.supplier}.` }
    },
  },
]

const SCRIPTS = { mechanic: { lines: SCRIPT, key: 'demo_step', loop: false }, owner: { lines: OWNER_SCRIPT, key: 'owner_demo_step', loop: true } }

export function scriptLine(i, role = 'mechanic') {
  return SCRIPTS[role].lines[i]
}

export function createDemoVoice({ onEvent, role = 'mechanic', uid = role === 'owner' ? 'o-asha' : 'm-raju' }) {
  const { lines, key, loop } = SCRIPTS[role]
  let step = store.get()[key] || 0
  let busy = false
  let listening = false
  let unsub = () => {}
  const timers = new Set()
  const later = (ms) => new Promise((r) => timers.add(setTimeout(r, ms)))

  async function stream(role, text, msPerWord = 70) {
    const words = text.split(' ')
    for (let i = 1; i <= words.length; i++) {
      onEvent({ type: 'transcript', role, text: words.slice(0, i).join(' '), final: i === words.length })
      await later(msPerWord)
    }
  }

  function speak(text) {
    if (!('speechSynthesis' in window)) return
    const u = new SpeechSynthesisUtterance(text)
    u.lang = 'en-IN'
    u.rate = 1.05
    window.speechSynthesis.cancel()
    window.speechSynthesis.speak(u)
  }

  async function reply(text) {
    onEvent({ type: 'thinking', on: false })
    onEvent({ type: 'speaking', on: true })
    speak(text)
    await stream('agent', text, 55)
    onEvent({ type: 'speaking', on: false })
    onEvent({ type: 'turn_complete' })
  }

  async function playNext() {
    if (busy) return
    if (loop) step %= lines.length
    const line = lines[step]
    if (!line) {
      busy = true
      await reply('That was the whole demo job. Reset the demo to run it again.')
      busy = false
      return
    }
    busy = true
    onEvent({ type: 'thinking', on: true })
    await stream(role, line.say, 90)
    if (line.note) onEvent({ type: 'note', text: line.note })
    await later(650)
    let out
    store.change((s) => {
      if (line.time) s.now = at(line.time)
      out = line.run(s)
      s[key] = step + 1
    })
    step += 1
    for (const [name, result] of out.tools) {
      onEvent({ type: 'tool', name, result })
      await later(260)
    }
    await reply(out.reply)
    busy = false
  }

  // Headset notices, e.g. "Ramesh approved. Go ahead." when the customer taps Approve in another tab.
  function watchNotices() {
    const check = () => {
      const pending = store.get().messages.filter((m) => m.to === uid && m.status === 'sent (simulated)')
      if (!pending.length || busy) return
      store.change((s) => s.messages.forEach((m) => { if (m.to === uid) m.status = 'delivered' }))
      busy = true
      ;(async () => {
        for (const m of pending.reverse()) {
          onEvent({ type: 'notice', text: m.text })
          await reply(m.text)
        }
        busy = false
      })()
    }
    unsub = store.subscribe(check)
    timers.add(setInterval(check, 1000))
  }

  return {
    demo: true,
    async connect() {
      onEvent({ type: 'status', status: 'connecting' })
      await later(500)
      if (role === 'mechanic') watchNotices()
      onEvent({ type: 'status', status: 'ready' })
    },
    startTalking() {
      if (busy) return
      listening = true
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
      onEvent({ type: 'listening', on: true })
    },
    stopTalking() {
      if (!listening) return
      listening = false
      onEvent({ type: 'listening', on: false })
      playNext()
    },
    sendText() {
      playNext()
    },
    // Fake mic level so the orb breathes while "listening".
    level() {
      return listening ? 0.35 + 0.3 * Math.abs(Math.sin(performance.now() / 140)) : 0
    },
    nextLine() {
      return lines[loop ? step % lines.length : step]?.say || ''
    },
    close() {
      unsub()
      timers.forEach((t) => { clearTimeout(t); clearInterval(t) })
      if ('speechSynthesis' in window) window.speechSynthesis.cancel()
      onEvent({ type: 'status', status: 'closed' })
    },
  }
}

export function resetDemo() {
  store.reset()
}
