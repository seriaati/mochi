import type { CapacitorConfig } from '@capacitor/cli'

// No server.url: the app asks for the server at its first start and adds it at runtime
// (MainActivity.load), so one app works with any Mochi.
const config: CapacitorConfig = {
  appId: 'moe.seria.mochi',
  appName: 'Mochi',
  // Never shown, but Capacitor needs a page to bundle.
  webDir: 'android/web',
  // So the window's background shows until the page paints, instead of white.
  backgroundColor: '#00000000',
}

export default config
