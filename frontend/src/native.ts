import type { AppPlugin } from '@capacitor/app'
import type { PluginListenerHandle } from '@capacitor/core'
import { useEffect, useEffectEvent, useSyncExternalStore } from 'react'
import type { Theme } from './theme.ts'

// The Android app (android/) is this web app in a WebView, loaded from the user's Mochi, with
// Capacitor's bridge in the page. Its plugins load only there (the service worker still caches
// their chunk with the rest of the build, as the app needs it offline too).
export const inApp = !!(window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.()

const app = inApp ? import('@capacitor/app') : null

// The app's own plugin: android/app/src/main/java/moe/seria/mochi/MochiPlugin.kt. Wrapped, as a
// plugin answers any property, `then` too, so a promise can't resolve to it.
type Mochi = {
  // The status and navigation bars take the page's color, with icons for a light or dark page;
  // mode is the picked theme, which the app's splash screen takes at the next start.
  setSystemBars(options: { color: string; dark: boolean; mode: Theme }): Promise<void>
  // Leaves this server (its login and push) for the app's screen that asks for one.
  changeServer(): Promise<void>
  // Maintenance reminders on this phone (src/push.ts). enabled: the server has the token, from
  // these Firebase settings; allowed: Android lets the app notify.
  pushState(): Promise<{ enabled: boolean; allowed: boolean; token?: string; firebase?: FirebaseSettings }>
  // Asks for permission to notify, then starts Firebase with the server's settings: the token for
  // the server. Rejects when notifying isn't allowed.
  enablePush(options: FirebaseSettings): Promise<{ token: string }>
  // Stops it: the token it had, for the server to drop.
  disablePush(): Promise<{ token?: string }>
  // The page a tapped notification opens, once: {} when there's none.
  takePath(): Promise<{ path?: string }>
  // A notification was tapped: takePath has its page.
  addListener(event: 'path', listener: () => void): Promise<PluginListenerHandle>
}
/** What the app starts Firebase with: GET /api/notifications/firebase. */
export type FirebaseSettings = { project_id: string; app_id: string; api_key: string; sender_id: string }
export const mochi = inApp
  ? import('@capacitor/core').then(({ registerPlugin }) => ({ plugin: registerPlugin<Mochi>('Mochi') }))
  : null

/** Adds an @capacitor/app listener in the app. Returns its removal, for an effect's cleanup. */
export function listen(add: (App: AppPlugin) => Promise<PluginListenerHandle>) {
  if (!app) return
  const handle = app.then(({ App }) => add(App))
  return () => void handle.then((h) => h.remove())
}

/** Android's Back in the app. `back` returns false when it has nothing left to do, and the app
 * goes to the background. */
export function useBackButton(back: (canGoBack: boolean) => boolean) {
  const onBack = useEffectEvent(back)
  useEffect(
    () =>
      listen((App) =>
        App.addListener('backButton', ({ canGoBack }) => {
          if (!onBack(canGoBack)) void App.minimizeApp()
        }),
      ),
    [],
  )
}

/** The page a tapped notification opens, as it's tapped and on mount, for a tap that came before
 * (the app starting, the login). */
export function useNotificationPath(open: (path: string) => void) {
  const onOpen = useEffectEvent(open)
  useEffect(() => {
    if (!mochi) return
    const handle = mochi.then(async ({ plugin }) => {
      const take = async () => {
        const { path } = await plugin.takePath()
        // A page of this web app, not another origin's.
        if (path?.startsWith('/') && !path.startsWith('//')) onOpen(path)
      }
      const listener = await plugin.addListener('path', () => void take())
      void take()
      return listener
    })
    return () => void handle.then((h) => h.remove())
  }, [])
}

// Releases of the app are on GitHub (.github/workflows/android.yml attaches mochi.apk). The app
// asks GitHub for the latest one when it starts and every few hours while open.
const RELEASE_CHECK_MS = 6 * 60 * 60 * 1000

let release: string | null = null // a newer app's APK
const releaseListeners = new Set<() => void>()

type Release = { tag_name: string; assets: { name: string; browser_download_url: string }[] }

/** The app's version (versionName: "dev" for a local build) and build (versionCode). */
export const appInfo = app?.then(({ App }) => App.getInfo())

void appInfo?.then(({ version }) => {
  const mine = semver(version)
  if (!mine) return // a local build (dev)
  const check = () =>
    fetch('https://api.github.com/repos/seriaati/mochi/releases/latest')
      .then((response) => (response.ok ? (response.json() as Promise<Release>) : null))
      .then((latest) => {
        const theirs = latest && semver(latest.tag_name)
        // No APK: a release from before the app, or one whose APK is still building.
        const apk = latest?.assets.find(({ name }) => name.endsWith('.apk'))
        if (!theirs || !apk || !newer(theirs, mine)) return
        release = apk.browser_download_url
        releaseListeners.forEach((listener) => listener())
      })
      .catch(() => undefined) // offline, or GitHub unreachable: next time
  void check()
  setInterval(() => void check(), RELEASE_CHECK_MS)
})

function semver(version: string): number[] | null {
  const match = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(version)
  return match && match.slice(1).map(Number)
}

function newer(a: number[], b: number[]): boolean {
  const i = a.findIndex((n, j) => n !== b[j])
  return i >= 0 && a[i] > b[i]
}

/** A newer release of the Android app: the URL of its APK. */
export function useAppUpdate(): string | null {
  return useSyncExternalStore(
    (listener) => {
      releaseListeners.add(listener)
      return () => releaseListeners.delete(listener)
    },
    () => release,
  )
}

/** Another host than the server's, so Capacitor hands it to the browser (Bridge.launchIntent),
 * which downloads it and offers to install it over this app. The WebView never loads it. */
export function applyAppUpdate(url: string) {
  location.assign(url)
}
