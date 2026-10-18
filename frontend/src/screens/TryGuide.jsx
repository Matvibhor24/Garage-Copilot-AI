// "Try a demo" guide on the mechanic screen, for people trying the hosted product (judges): one job, end to end.
// Each line can be tapped to send it as typed text, for anyone without a mic.
import { useEffect, useRef } from 'react'
import { TRY } from '../config.js'

const STEPS = [
  { say: 'New bike, Splendor Plus, MH12 AB 1234, owner Ramesh, clutch slipping, service too.',
    what: "Opens a job card, recalls the bike's history and sends Ramesh his live tracking link." },
  { say: 'Started service.', what: "Moves the job on. The owner's 3D floor updates live." },
  { say: 'Clutch lever free play?', what: "Answers from the owner's manual, with the page number." },
  { say: 'Why is it hard to start in the morning?', what: 'Not in the manual, so it asks before searching the web. Say “yes”.' },
  { say: 'Do we have a clutch plate for Splendor? Price?', what: 'Checks stock, price and labour.' },
  { say: 'Show Ramesh the worn plate.', what: 'Take a photo with the camera button first. Sends Ramesh a quote in his language.' },
  { what: 'Tap “Customer view ↗” on the job card, approve the quote there, then come back: the agent tells you.' },
  { say: 'Used one clutch plate set.', what: 'Logs the part and its fittings. Low stock asks the owner to reorder.' },
  { say: 'Move it to washing.' },
  { say: 'Job done.', what: 'Closes the job and says the final bill.' },
]

export default function TryGuide({ onClose, onSay }) {
  const dialog = useRef(null)
  useEffect(() => { dialog.current?.showModal() }, [])

  return (
    <dialog ref={dialog} className="v3d-dialog try-guide" onClose={onClose}
      onClick={(e) => e.target === dialog.current && dialog.current.close()} aria-labelledby="try-title">
      <div className="v3d-dialog-body">
        <div className="row between">
          <div className="stack" style={{ '--gap': '2px' }}>
            <span className="eyebrow">Try a demo</span>
            <h2 id="try-title">One bike, start to finish</h2>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => dialog.current.close()} autoFocus>Close</button>
        </div>
        <p className="muted small">
          {onSay ? 'Say each line, or tap it to send it as text.' : 'Tap Start first, then say each line (or come back here and tap it).'}
          {' '}English, Hindi or Marathi all work.
        </p>
        <ol className="try-steps">
          {STEPS.map((s, i) => (
            <li key={i}>
              {s.say && (
                <button className="try-say" disabled={!onSay} onClick={() => { onSay(s.say); dialog.current.close() }}>
                  “{s.say}”
                </button>
              )}
              {s.what && <span className="muted small">{s.what}</span>}
            </li>
          ))}
        </ol>
        <div className="try-more small">
          <p><strong>Stays on the job:</strong> ask it to “explain photosynthesis”. It cuts the answer off and offers garage help instead.</p>
          {TRY && (
            <p><strong>Owner view:</strong> open <a href="/owner" target="_blank" rel="noopener noreferrer">/owner</a> and sign in
              with <span className="mono">{TRY.ownerPhone}</span>, code <span className="mono">{TRY.ownerCode}</span>: the live 3D floor,
              stock, money, and a voice assistant for the owner.</p>
          )}
        </div>
      </div>
    </dialog>
  )
}
