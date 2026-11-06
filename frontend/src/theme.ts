import { mochi } from './native.ts'

/** Light, dark, or following the system. Kept per browser; index.html applies it before first paint. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'theme'

// --bg in index.css
const GROUND = { light: '#efeeea', dark: '#0e0e0d' }

const systemDark = window.matchMedia('(prefers-color-scheme: dark)')

export function savedTheme(): Theme {
  try {
    const theme = localStorage.getItem(KEY)
    return theme === 'light' || theme === 'dark' ? theme : 'system'
  } catch {
    return 'system'
  }
}

function resolvedTheme(): 'light' | 'dark' {
  const theme = document.documentElement.dataset.theme
  if (theme === 'light' || theme === 'dark') return theme
  return systemDark.matches ? 'dark' : 'light'
}

function setSystemBars() {
  const theme = resolvedTheme()
  const mode = document.documentElement.dataset.theme ? theme : 'system'
  void mochi?.then(({ plugin }) => plugin.setSystemBars({ color: GROUND[theme], dark: theme === 'dark', mode }))
}

/** Keeps the Android app's system bars on the page's theme. */
export function followTheme() {
  if (!mochi) return
  setSystemBars()
  systemDark.addEventListener('change', setSystemBars)
}

/** Switches the theme, cross-fading where the browser can, and remembers it. */
export function applyTheme(theme: Theme) {
  const set = () => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
    setSystemBars()
  }
  if (document.startViewTransition) document.startViewTransition(set)
  else set()
  try {
    if (theme === 'system') localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, theme)
  } catch {
    // Storage blocked: the choice lasts until the page reloads.
  }
}
