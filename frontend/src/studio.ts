import type { Settings } from './settings/queries.ts'

/**
 * The studio name and logo, kept per browser from the last settings load. The login screen
 * can't read settings, and the top bar and tab title show them before settings load;
 * index.html applies the name to the title before first paint.
 */

export type Studio = Pick<Settings, 'studio_name' | 'studio_logo'>

const KEY = 'studio'

export function savedStudio(): Studio | null {
  try {
    const saved = localStorage.getItem(KEY)
    return saved ? (JSON.parse(saved) as Studio) : null
  } catch {
    return null // storage blocked or unreadable: the defaults show until settings load
  }
}

export function rememberStudio({ studio_name, studio_logo }: Studio) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ studio_name, studio_logo }))
  } catch {
    // Storage blocked or full: the defaults show next time until settings load.
  }
}
