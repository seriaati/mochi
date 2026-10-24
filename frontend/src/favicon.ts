import { useEffect } from 'react'

/**
 * The tab icon: the studio logo when one is set, else the plain mark in public/favicon.svg.
 * The logo's icon is kept per browser; index.html applies it before first paint.
 */

const DEFAULT = '/favicon.svg'
const KEY = 'favicon'
/** Pixels per side: sharp at the usual 32px on 2x screens, and only a few KB. */
const SIZE = 64
/** Corner radius per pixel of height, as on the top bar's logo (7px at 26px tall). */
const RADIUS = 7 / 26

/** The logo fitted into a transparent square with rounded corners, as a PNG data: URL. */
async function iconFrom(logo: string): Promise<string> {
  const image = new Image()
  image.src = logo
  await image.decode()
  const scale = SIZE / Math.max(image.naturalWidth, image.naturalHeight)
  const width = image.naturalWidth * scale
  const height = image.naturalHeight * scale
  const x = (SIZE - width) / 2
  const y = (SIZE - height) / 2
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = SIZE
  const context = canvas.getContext('2d')!
  context.imageSmoothingQuality = 'high'
  context.beginPath()
  context.roundRect(x, y, width, height, height * RADIUS)
  context.clip()
  context.drawImage(image, x, y, width, height)
  return canvas.toDataURL('image/png')
}

function show(href: string) {
  const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (!link) return
  link.type = href === DEFAULT ? 'image/svg+xml' : 'image/png'
  link.href = href
}

function remember(icon: string | null) {
  try {
    if (icon === null) localStorage.removeItem(KEY)
    else localStorage.setItem(KEY, icon)
  } catch {
    // Storage blocked: the default mark shows until settings load.
  }
}

/** Follows the studio logo: undefined while settings load, null without one. */
export function useFavicon(logo: string | null | undefined) {
  useEffect(() => {
    if (logo === undefined) return
    if (logo === null) {
      show(DEFAULT)
      remember(null)
      return
    }
    let current = true
    iconFrom(logo)
      .then((icon) => {
        if (!current) return
        show(icon)
        remember(icon)
      })
      .catch(() => {}) // a logo the browser can't decode keeps the current icon
    return () => {
      current = false
    }
  }, [logo])
}
