import type { AppPlugin } from '@capacitor/app'
import type { PluginListenerHandle } from '@capacitor/core'
import { useEffect, useEffectEvent, useSyncExternalStore } from 'react'
import type { Theme } from './theme.ts'

export const inApp = !!(window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor?.isNativePlatform?.()

const app = inApp ? import('@capacitor/app') : null

// android/app/src/main/java/moe/seria/mochi/MochiPlugin.kt
type Mochi = {
  setSystemBars(options: { color: string; dark: boolean; mode: Theme }): Promise<void>
  changeServer(): Promise<void>
  pushState(): Promise<{ enabled: boolean; allowed: boolean; token?: string; firebase?: FirebaseSettings }>
  enablePush(options: FirebaseSettings): Promise<{ token: string }>
  disablePush(): Promise<{ token?: string }>
  takePath(): Promise<{ path?: string }>
  addListener(event: 'path', listener: () => void): Promise<PluginListenerHandle>
}
export type FirebaseSettings = { project_id: string; app_id: string; api_key: string; sender_id: string }
// Wrapped, as a plugin answers any property, `then` too, so a promise can't resolve to it.
export const mochi = inApp
  ? import('@capacitor/core').then(({ registerPlugin }) => ({ plugin: registerPlugin<Mochi>('Mochi') }))
  : null

export function listen(add: (App: AppPlugin) => Promise<PluginListenerHandle>) {
  if (!app) return
  const handle = app.then(({ App }) => add(App))
  return () => void handle.then((h) => h.remove())
}

/** `back` returns false when it has nothing left to do, and the app goes to the background. */
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

/** Also on mount, for a notification tapped before the page was up (a cold start, the login). */
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

const RELEASE_CHECK_MS = 6 * 60 * 60 * 1000

let release: string | null = null // a newer release's APK
const releaseListeners = new Set<() => void>()

type Release = { tag_name: string; assets: { name: string; browser_download_url: string }[] }

export const appInfo = app?.then(({ App }) => App.getInfo())

void appInfo?.then(({ version }) => {
  const mine = semver(version)
  if (!mine) return // a local build: "dev"
  const check = () =>
    fetch('https://api.github.com/repos/seriaati/mochi/releases/latest')
      .then((response) => (response.ok ? (response.json() as Promise<Release>) : null))
      .then((latest) => {
        const theirs = latest && semver(latest.tag_name)
        // No APK yet while the release's build is still running.
        const apk = latest?.assets.find(({ name }) => name.endsWith('.apk'))
        if (!theirs || !apk || !newer(theirs, mine)) return
        release = apk.browser_download_url
        releaseListeners.forEach((listener) => listener())
      })
      .catch(() => undefined)
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

export function useAppUpdate(): string | null {
  return useSyncExternalStore(
    (listener) => {
      releaseListeners.add(listener)
      return () => releaseListeners.delete(listener)
    },
    () => release,
  )
}

// Capacitor hands another host's URL to the browser, which downloads the APK and offers to
// install it over the app.
export function applyAppUpdate(url: string) {
  location.assign(url)
}
