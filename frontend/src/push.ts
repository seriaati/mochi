import { api, ApiError } from './api.ts'
import { mochi, type FirebaseSettings } from './native.ts'

// The web app, not the native code, registers the app's FCM token: only it knows the API's
// address (VITE_API_URL).

/** Null when the server isn't set up for push, as on the demo. */
export async function firebaseSettings(): Promise<FirebaseSettings | null> {
  try {
    return await api.get<FirebaseSettings>('/notifications/firebase')
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

export async function enablePush() {
  const settings = await firebaseSettings()
  if (!settings) throw new Error("This Mochi server isn't set up for notifications in the app")
  const { plugin } = await mochi!
  const { token } = await plugin.enablePush(settings)
  try {
    await api.put('/notifications/fcm', { token })
  } catch (error) {
    await plugin.disablePush()
    throw error
  }
}

export async function disablePush() {
  const { plugin } = await mochi!
  const { token } = await plugin.disablePush()
  // Best effort: the server drops a token FCM deleted at its next send anyway.
  if (token) await api.delete('/notifications/fcm', { token }).catch(() => undefined)
}

let sync: Promise<void> | undefined

/** Once per start: re-registers the token, which Firebase may have replaced while the app was
 * closed, and follows the server's Firebase settings if they changed or are gone. */
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
      // A token from the old Firebase project is no use.
      token = (await plugin.enablePush(settings)).token
      if (state.token) await api.delete('/notifications/fcm', { token: state.token }).catch(() => undefined)
    }
    await api.put('/notifications/fcm', { token })
  })().catch(() => undefined)
  return sync
}
