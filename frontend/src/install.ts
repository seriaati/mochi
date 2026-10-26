import { useSyncExternalStore } from 'react'

/**
 * The browser's offer to install the app, kept for the nav's install button on phones and
 * tablets. Browsers only make the offer while the app isn't installed, and only where they can
 * install on tap (Chrome and friends on Android, not iOS).
 */

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<{ outcome: 'accepted' | 'dismissed' }>
}

let offer: BeforeInstallPromptEvent | null = null
const listeners = new Set<() => void>()

function set(next: BeforeInstallPromptEvent | null) {
  offer = next
  listeners.forEach((listener) => listener())
}

// Listening from page load, as the offer can come before the app renders, e.g. on login.
if (matchMedia('(pointer: coarse)').matches) {
  addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault() // the nav's button offers it, instead of the browser's own banner
    set(event as BeforeInstallPromptEvent)
  })
  addEventListener('appinstalled', () => set(null))
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** Opens the install prompt, or null when there's nothing to offer. */
export function useInstall(): (() => void) | null {
  const current = useSyncExternalStore(subscribe, () => offer)
  if (!current) return null
  return () => {
    // An offer can be used once; if it's dismissed, the browser makes a new one on a later visit.
    set(null)
    current.prompt().catch(() => {})
  }
}
