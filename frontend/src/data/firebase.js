// Firebase is optional: without VITE_FIREBASE_* the app runs on dev tokens and polling.
import { FIREBASE, FIRESTORE_EMULATOR_HOST } from '../config.js'

let ready = null

// Lazily load and initialise Firebase (keeps it out of the first paint and out of demo builds).
export function firebase() {
  if (!FIREBASE) return Promise.resolve(null)
  if (!ready) {
    ready = (async () => {
      const [{ initializeApp }, auth, fs] = await Promise.all([
        import('firebase/app'),
        import('firebase/auth'),
        import('firebase/firestore'),
      ])
      const app = initializeApp(FIREBASE)
      // Offline cache: screens keep working and stay readable on patchy garage internet.
      const db = fs.initializeFirestore(app, { localCache: fs.persistentLocalCache() })
      if (FIRESTORE_EMULATOR_HOST) {
        const [host, port] = FIRESTORE_EMULATOR_HOST.split(':')
        fs.connectFirestoreEmulator(db, host, Number(port))
      }
      return { app, auth: auth.getAuth(app), db, authLib: auth, fs }
    })()
  }
  return ready
}
