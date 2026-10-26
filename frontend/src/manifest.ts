import { iconFrom } from './favicon.ts'
import type { Studio } from './studio.ts'

/**
 * The installed app's name and icon: the studio's, else the defaults vite.config.ts builds into
 * /manifest.webmanifest. A file can't change per studio, so the studio's manifest is made here,
 * as a blob: URL on this origin. Browsers read it when the app is installed, so a new name or
 * logo shows on reinstall.
 */

const DEFAULT = '/manifest.webmanifest'
/** The latest call, so a slower earlier one doesn't overwrite it. */
let latest = 0

export async function showManifest(studio: Studio | null) {
  const call = ++latest
  const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]')
  if (!link) return // the dev server has no manifest
  const touch = document.querySelector<HTMLLinkElement>('link[rel="apple-touch-icon"]')!
  const previous = link.href
  const show = (href: string, touchIcon: string) => {
    if (call !== latest) return
    link.href = href
    touch.href = touchIcon
    if (previous.startsWith('blob:')) URL.revokeObjectURL(previous)
  }

  if (!studio?.studio_name && !studio?.studio_logo) return show(DEFAULT, '/apple-touch-icon.png')
  try {
    const manifest = await (await fetch(DEFAULT)).json()
    // A blob: URL can't resolve relative URLs, so every URL in it is absolute.
    const url = (path: string) => new URL(path, location.origin).href
    manifest.id = manifest.start_url = url(manifest.start_url)
    manifest.scope = url(manifest.scope)
    manifest.icons = manifest.icons.map((icon: { src: string }) => ({ ...icon, src: url(icon.src) }))
    if (studio.studio_name) manifest.name = manifest.short_name = studio.studio_name
    let touchIcon = '/apple-touch-icon.png'
    if (studio.studio_logo) {
      const [small, large] = await Promise.all([192, 512].map((size) => iconFrom(studio.studio_logo!, size)))
      manifest.icons = [
        { src: small, sizes: '192x192', type: 'image/png' },
        { src: large, sizes: '512x512', type: 'image/png' },
      ]
      touchIcon = small
    }
    const blob = new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' })
    show(URL.createObjectURL(blob), touchIcon)
  } catch {
    // Offline before the manifest was cached, or a logo the browser can't decode: the
    // current manifest stays.
  }
}
