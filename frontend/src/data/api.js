// The one way screens talk to the backend. In demo mode the same calls go to the in-browser fake.
import { API_BASE, DEMO } from '../config.js'
import { idToken } from './auth.js'

export class ApiError extends Error {
  constructor(status, message) {
    super(message)
    this.status = status
  }
}

export function requestId() {
  return crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).slice(2) + Date.now()
}

export async function api(path, { method = 'GET', body, rawBody, contentType, anonymous = false } = {}) {
  if (DEMO) {
    const demo = await import('../demo/server.js')
    return demo.handle(method, path, body, rawBody)
  }
  const headers = {}
  if (!anonymous) {
    const token = await idToken()
    if (token) headers.Authorization = `Bearer ${token}`
  }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (rawBody !== undefined) headers['Content-Type'] = contentType
  let res
  try {
    res = await fetch(API_BASE + path, { method, headers, body: rawBody ?? (body !== undefined ? JSON.stringify(body) : undefined) })
  } catch {
    throw new ApiError(0, 'No connection. Retrying…')
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, data.detail || `Request failed (${res.status})`)
  return data
}
