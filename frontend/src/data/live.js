// useLiveView: load a view from the API and keep it fresh.
//   - Firebase configured: a Firestore listener on the underlying docs triggers a refetch (no polling).
//   - Demo mode: the fake backend emits change events.
//   - Otherwise: poll every few seconds.
// Also refetches when the tab becomes visible again.
import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO } from '../config.js'
import { firebase } from './firebase.js'

const POLL_MS = 4000

export function useLiveView(load, { watch = [], firestore = null, deps = [], enabled = true, animate = false } = {}) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const loadRef = useRef(load)
  loadRef.current = load
  const last = useRef('')

  const reload = useCallback(async () => {
    try {
      const data = await loadRef.current()
      const json = JSON.stringify(data)
      if (json === last.current) return setState((s) => (s.error ? { ...s, error: null } : s))
      const first = !last.current
      last.current = json
      const apply = () => setState({ data, error: null, loading: false })
      // animate: let the browser morph elements with a view-transition-name (e.g. a job card changing column)
      if (animate && !first && document.startViewTransition && !document.hidden) {
        const { flushSync } = await import('react-dom')
        document.startViewTransition(() => flushSync(apply))
      } else apply()
    } catch (error) {
      setState((s) => ({ ...s, error, loading: false }))
    }
  }, [animate])

  useEffect(() => {
    if (!enabled) return
    let stop = () => {}
    let timer = null
    let cancelled = false
    const soon = () => {
      clearTimeout(timer)
      timer = setTimeout(reload, 120)
    }
    reload()

    ;(async () => {
      if (DEMO) {
        const demo = await import('../demo/server.js')
        stop = demo.subscribe(soon)
        return
      }
      const fb = firestore ? await firestore : await firebase()
      if (cancelled) return
      if (fb && watch.length) {
        const unsubs = watch.map((w) => fb.fs.onSnapshot(toRef(fb, w), soon, () => {}))
        stop = () => unsubs.forEach((u) => u())
      } else {
        const id = setInterval(reload, POLL_MS)
        stop = () => clearInterval(id)
      }
    })()

    const onVisible = () => document.visibilityState === 'visible' && reload()
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      cancelled = true
      clearTimeout(timer)
      stop()
      document.removeEventListener('visibilitychange', onVisible)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, reload, ...deps])

  return { ...state, reload }
}

// Watch descriptors: "garages/g/jobs/J-1" (doc), "garages/g/jobs" (collection),
// or ["garages/g/quotes", "job_id", "==", "J-1"] (query).
function toRef(fb, w) {
  const { fs, db } = fb
  if (Array.isArray(w)) {
    const [path, field, op, value] = w
    return fs.query(fs.collection(db, path), fs.where(field, op, value))
  }
  const parts = w.split('/').length
  return parts % 2 === 0 ? fs.doc(db, w) : fs.collection(db, w)
}
