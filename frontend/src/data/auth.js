// Who is signed in. Three modes:
//   firebase - real Firebase Auth (phone OTP for owners, name + PIN custom token for mechanics)
//   dev      - no Firebase config: the backend runs with AUTH_DISABLED=1 and accepts "dev:<garage>:<uid>:<role>"
//   demo     - VITE_DEMO=1: the in-browser fake backend
import { DEMO, FIREBASE } from '../config.js'
import { firebase } from './firebase.js'

const KEY = 'gc.session'

// Owners stay signed in on their device (localStorage). A mechanic's session belongs to one tab on the shared
// garage phone (sessionStorage): it survives a reload of the mechanic screen but not closing the tab.
function load() {
  for (const store of [sessionStorage, localStorage]) {
    try {
      const s = JSON.parse(store.getItem(KEY))
      if (s) return s
    } catch { /* private mode */ }
  }
  return null
}
function save(s) {
  try {
    if (!s) (sessionStorage.getItem(KEY) ? sessionStorage : localStorage).removeItem(KEY)
    else (s.role === 'mechanic' ? sessionStorage : localStorage).setItem(KEY, JSON.stringify(s))
  } catch { /* private mode */ }
}

export const MODE = DEMO ? 'demo' : FIREBASE ? 'firebase' : 'dev'

export function session() {
  return load()
}

export async function idToken() {
  const s = load()
  if (!s) return ''
  if (s.mode === 'firebase') {
    const fb = await firebase()
    const user = fb?.auth.currentUser || (await waitForUser(fb))
    return user ? user.getIdToken() : ''
  }
  return s.token || ''
}

async function waitForUser(fb) {
  if (!fb) return null
  await fb.auth.authStateReady()
  return fb.auth.currentUser
}

// Mechanic on the shared garage phone. `api` is passed in to avoid an import cycle.
export async function signInWithPin(api, garageId, name, pin) {
  const out = await api('/api/auth/pin', { method: 'POST', body: { garage_id: garageId, name, pin }, anonymous: true })
  const claims = out.claims
  if (out.custom_token && MODE === 'firebase') {
    const fb = await firebase()
    await fb.authLib.signInWithCustomToken(fb.auth, out.custom_token)
    save({ mode: 'firebase', role: claims.role, garage: claims.garage, name: claims.name })
  } else {
    save({ mode: MODE, role: claims.role, garage: claims.garage, name: claims.name, token: out.dev_token })
  }
  return load()
}

// Owner, local development without Firebase (backend AUTH_DISABLED=1), and demo mode.
export function signInDev(garage, uid, role, name) {
  save({ mode: MODE, role, garage, name, token: `dev:${garage}:${uid}:${role}` })
  return load()
}

// Owner phone OTP. Step 1 sends the SMS; step 2 confirms the code and attaches the garage claim.
export async function startPhoneSignIn(phone, buttonId) {
  const fb = await firebase()
  const verifier = new fb.authLib.RecaptchaVerifier(fb.auth, buttonId, { size: 'invisible' })
  return fb.authLib.signInWithPhoneNumber(fb.auth, phone, verifier)
}

export async function confirmPhoneSignIn(api, confirmation, code) {
  const cred = await confirmation.confirm(code)
  let token = await cred.user.getIdTokenResult()
  if (!token.claims.garage) {
    save({ mode: 'firebase' })
    await api('/api/auth/claim', { method: 'POST' })
    token = await cred.user.getIdTokenResult(true)
  }
  const c = token.claims
  save({ mode: 'firebase', role: c.role, garage: c.garage, name: c.name })
  return load()
}

// Customer link: a custom token scoped to one job, only used to listen to Firestore live.
export async function customerFirestore(api, linkToken) {
  if (MODE !== 'firebase') return null
  const fb = await firebase()
  const { custom_token } = await api(`/api/j/${linkToken}/session`, { method: 'POST', anonymous: true })
  await fb.authLib.signInWithCustomToken(fb.auth, custom_token)
  return fb
}

export async function signOut() {
  const s = load()
  save(null) // at once, so nothing can read the old session while Firebase signs out
  if (s?.mode === 'firebase') {
    const fb = await firebase()
    await fb?.auth.signOut()
  }
}
