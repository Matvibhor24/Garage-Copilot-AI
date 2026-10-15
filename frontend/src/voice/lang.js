// The reply language of a voice screen (C11). Auto (default) = the agent answers in whatever language it was just
// spoken to in; a pinned language goes to the backend with the session start (/ws/voice?lang=hi). Per device.
export const LANGS = [
  { code: 'auto', label: 'Auto' },
  { code: 'en', label: 'English' },
  { code: 'hi', label: 'हिंदी' },
  { code: 'mr', label: 'मराठी' },
]

const key = (role) => `gc.lang.${role}`

export function readLang(role) {
  try {
    const v = localStorage.getItem(key(role))
    return LANGS.some((l) => l.code === v) ? v : 'auto'
  } catch {
    return 'auto'
  }
}

export function saveLang(role, code) {
  try { localStorage.setItem(key(role), code) } catch { /* private mode */ }
}

// The query part the gateway reads: nothing for Auto.
export function langParam(code) {
  return code && code !== 'auto' && LANGS.some((l) => l.code === code) ? `&lang=${code}` : ''
}
