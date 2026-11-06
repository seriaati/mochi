import type { CapacitorConfig } from '@capacitor/cli'

// The Android app (android/): a WebView on the user's own Mochi web app, at its own origin, so its
// API calls, the service worker and the session cookie work as in a browser. No server here: the
// app asks for it at its first start (ServerActivity) and adds it as server.url at runtime
// (MainActivity.load), so one app works with any Mochi.
const config: CapacitorConfig = {
  appId: 'moe.seria.mochi',
  appName: 'Mochi',
  // Never shown: the app loads the server. Capacitor needs a page to bundle all the same.
  webDir: 'android/web',
  // See-through until the page paints, so the window's ground (res/values) shows, not white.
  backgroundColor: '#00000000',
}

export default config
