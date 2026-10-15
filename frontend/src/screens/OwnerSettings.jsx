// Owner > Settings: the garage's settings with a one-line explanation each (C09).
// Numbers are plain text inputs: the server checks the range and says what is wrong in words.
import { useEffect, useState } from 'react'
import { api, requestId } from '../data/api.js'
import { rupees } from '../format.js'
import { ErrorNote, Skeleton, Spinner, useToast } from '../ui.jsx'

const FIELDS = [
  { key: 'quote_limit', label: 'Auto-approve limit (₹)', type: 'number',
    help: 'Quotes up to this amount are approved without asking the customer. 0 = always ask the customer.' },
  { key: 'name', label: 'Garage name', help: 'Shown on the customer page and in WhatsApp messages.' },
  { key: 'city', label: 'City', help: 'Shown next to the garage name.' },
  { key: 'lang', label: 'Default customer language', type: 'lang',
    help: 'New customers get messages in this language unless the mechanic says otherwise.' },
  { key: 'supplier', label: 'Supplier', help: 'Who reorders go to when you say “Yes, reorder”.' },
  { key: 'reorder_qty', label: 'Reorder quantity', type: 'number',
    help: 'How many to order, for parts that don’t set their own.' },
  { key: 'low_at', label: 'Low-stock level', type: 'number',
    help: 'A part counts as low at or below this many, unless it sets its own level.' },
]

export default function OwnerSettings({ onSaved }) {
  const toast = useToast()
  const [saved, setSaved] = useState(null)
  const [form, setForm] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  async function load() {
    setError(null)
    try {
      const s = await api('/api/owner/settings')
      setSaved(s)
      setForm(s)
    } catch (e) {
      setError(e)
    }
  }
  useEffect(() => { load() }, [])

  if (!form) return error ? <ErrorNote error={error} onRetry={load} /> : <Skeleton h={420} style={{ borderRadius: 24 }} />

  const changes = Object.fromEntries(FIELDS.filter((f) => String(form[f.key]) !== String(saved[f.key])).map((f) => [f.key, form[f.key]]))
  const dirty = Object.keys(changes).length > 0

  async function save(e) {
    e.preventDefault()
    setBusy(true)
    try {
      const out = await api('/api/owner/settings', { method: 'PUT', body: { changes, request_id: requestId() } })
      setSaved(out.settings)
      setForm(out.settings)
      toast(out.summary ? out.summary[0].toUpperCase() + out.summary.slice(1) : 'Saved')
      onSaved?.()
    } catch (err) {
      toast(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card settings enter" onSubmit={save} aria-label="Garage settings">
      <div className="row between wrap" style={{ marginBottom: 6 }}>
        <h2>Settings</h2>
        <span className="muted small">Auto-approve now: {Number(saved.quote_limit) === 0 ? 'always ask the customer' : `up to ${rupees(saved.quote_limit)}`}</span>
      </div>
      <div className="settings-grid">
        {FIELDS.map((f) => (
          <div key={f.key} className={`field ${f.key === 'quote_limit' ? 'field-wide' : ''}`}>
            <label htmlFor={`set-${f.key}`}>{f.label}</label>
            {f.type === 'lang' ? (
              <select id={`set-${f.key}`} className="input" value={form.lang} onChange={(e) => setForm({ ...form, lang: e.target.value })}>
                {Object.entries(saved.languages || {}).map(([code, name]) => <option key={code} value={code}>{name}</option>)}
              </select>
            ) : (
              <input id={`set-${f.key}`} className="input" type="text" inputMode={f.type === 'number' ? 'numeric' : undefined}
                value={form[f.key] ?? ''}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })} aria-describedby={`help-${f.key}`} />
            )}
            <span id={`help-${f.key}`} className="muted small">{f.help}</span>
          </div>
        ))}
      </div>
      <div className="row" style={{ '--gap': '8px', marginTop: 18, justifyContent: 'flex-end' }}>
        <button type="button" className="btn btn-ghost" disabled={!dirty || busy} onClick={() => setForm(saved)}>Undo changes</button>
        <button className="btn btn-primary" disabled={!dirty || busy}>{busy ? <Spinner /> : 'Save'}</button>
      </div>
    </form>
  )
}
