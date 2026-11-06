import { api, ApiError } from './api.ts'
import { mochi, type FirebaseSettings } from './native.ts'

// Maintenance reminders as notifications in the Android app, through FCM: the app shows them
// (android/…/Notifications.kt). Only the web app knows the API's address (VITE_API_URL), so it
// fetches the server's Firebase settings, hands them to the app, and registers the token the app
// gets in return.

/** The server's Firebase settings for the app, or null when it isn't set up for push (the demo
 * isn't either). */
export async function firebaseSettings(): Promise<FirebaseSettings | null> {
  try {
    return await api.get<FirebaseSettings>('/notifications/firebase')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

/** Turns push on in this app: the server gets its token. */
export async function enablePush() {
  const settings = await firebaseSettings()
  if (!settings) throw new Error("This Mochi server isn't set up for notifications in the app")
  const { plugin } = await mochi!
  const { token } = await plugin.enablePush(settings)
  try {
    await api.put('/notifications/fcm', { token })
  } catch (error) {
    await plugin.disablePush() // the server has no token: not on
    throw error
  }
}

/** Turns push off in this app, and the server drops its token. */
export async function disablePush() {
  const { plugin } = await mochi!
  const { token } = await plugin.disablePush()
  // Best effort: FCM deleted the token, and the server drops it at its next send all the same.
  if (token) await api.delete('/notifications/fcm', { token }).catch(() => undefined)
}

let sync: Promise<void> | undefined

/** Once per start of the app, logged in: the server gets the token again, as Firebase may have
 * replaced it (MessagingService.onNewToken) or the server lost it, and push follows the server's
 * Firebase settings: off once it has none, on again with new ones. Never rejects; offline, the
 * next start tries again. */
export function syncPush(): Promise<void> {
  sync ??= (async () => {
    if (!mochi) return
    const { plugin } = await mochi
    const state = await plugin.pushState()
    if (!state.enabled) return
    const settings = await firebaseSettings()
    if (!settings) return disablePush()
    let token = state.token!
    const kept = state.firebase
    if (!kept || (Object.keys(settings) as (keyof FirebaseSettings)[]).some((key) => settings[key] !== kept[key])) {
      // Another Firebase project, whose token is new; the old one's is no use.
      token = (await plugin.enablePush(settings)).token
      if (state.token) await api.delete('/notifications/fcm', { token: state.token }).catch(() => undefined)
    }
    await api.put('/notifications/fcm', { token })
  })().catch(() => undefined)
  return sync
}
