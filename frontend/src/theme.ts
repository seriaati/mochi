/** Light, dark, or following the system. Kept per browser; index.html applies it before first paint. */
export type Theme = 'system' | 'light' | 'dark'

const KEY = 'theme'

export function savedTheme(): Theme {
  try {
    const theme = localStorage.getItem(KEY)
    return theme === 'light' || theme === 'dark' ? theme : 'system'
  } catch {
    return 'system'
  }
}

/** Switches the theme, cross-fading where the browser can, and remembers it. */
export function applyTheme(theme: Theme) {
  const set = () => {
    if (theme === 'system') delete document.documentElement.dataset.theme
    else document.documentElement.dataset.theme = theme
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
