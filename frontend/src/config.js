// Settings from VITE_* env vars (see .env.example). Nothing secret lives in the frontend.
const env = import.meta.env

export const DEMO = env.VITE_DEMO === '1'
export const API_BASE = (env.VITE_API_BASE || '').replace(/\/$/, '')
// The garage the landing page's "Call the garage" button calls (C15/C16)
export const FRONT_DESK_GARAGE = env.VITE_FRONT_DESK_GARAGE || 'shree-auto'
export const FRONT_DESK_GARAGE_NAME = env.VITE_FRONT_DESK_GARAGE_NAME || 'Shree Auto'

export const FIREBASE = env.VITE_FIREBASE_API_KEY
  ? {
      apiKey: env.VITE_FIREBASE_API_KEY,
      authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
      projectId: env.VITE_FIREBASE_PROJECT_ID,
      appId: env.VITE_FIREBASE_APP_ID,
    }
  : null
export const FIRESTORE_EMULATOR_HOST = env.VITE_FIRESTORE_EMULATOR_HOST || ''

// Firebase Hosting rewrites do not carry WebSockets, so in production the voice socket goes straight to
// Cloud Run (VITE_WS_BASE, e.g. wss://garage-copilot-xxxx.a.run.app). Locally, the Vite proxy handles /ws.
export function wsBase() {
  const base = (env.VITE_WS_BASE || API_BASE || window.location.origin).replace(/\/$/, '')
  return base.replace(/^http/, 'ws')
}
