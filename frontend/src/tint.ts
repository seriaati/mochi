import { useEffect, useState } from 'react'

/** Pastel tints in mockup order; the matching .tint-* classes live in index.css. */
const tints = ['peach', 'blue', 'lavender', 'yellow', 'sage', 'teal'] as const

type Tint = (typeof tints)[number]

/** A stable tint class for a record, e.g. a client card. */
export function tintClass(id: number): string {
  return `tint-${tints[id % tints.length]}`
}

/** Hue (0–360) and saturation, value (0–1) of an RGB colour. */
function hsv(r: number, g: number, b: number): [number, number, number] {
  const max = Math.max(r, g, b)
  const range = max - Math.min(r, g, b)
  let hue = 0
  if (range > 0) {
    if (max === r) hue = ((g - b) / range) % 6
    else if (max === g) hue = (b - r) / range + 2
    else hue = (r - g) / range + 4
  }
  return [(hue * 60 + 360) % 360, max ? range / max : 0, max / 255]
}

const hueGap = (a: number, b: number) => Math.min(Math.abs(a - b), 360 - Math.abs(a - b))

let tintHues: [Tint, number][] | undefined

/** Each tint's hue, read from its .tint-* class so it follows index.css. */
function readTintHues(): [Tint, number][] {
  tintHues ??= tints.map((tint) => {
    const probe = document.createElement('span')
    probe.className = `tint-${tint}`
    document.body.append(probe)
    const [r, g, b] = getComputedStyle(probe).backgroundColor.match(/\d+(\.\d+)?/g)!.map(Number)
    probe.remove()
    return [tint, hsv(r, g, b)[0]]
  })
  return tintHues
}

/**
 * The tint closest in hue to the image's main colour, or null when it has none to speak of
 * (mostly grey, black or white) or can't be read.
 */
async function matchTint(url: string): Promise<Tint | null> {
  const image = new Image()
  image.crossOrigin = 'anonymous' // Discord's CDN allows it; without it the pixels can't be read
  image.src = url
  await image.decode()
  const size = 32
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const context = canvas.getContext('2d', { willReadFrequently: true })!
  context.drawImage(image, 0, 0, size, size)
  const pixels = context.getImageData(0, 0, size, size).data

  // Hues in 15° bins, each pixel weighted by how colourful it is.
  const bins = new Array<number>(24).fill(0)
  let total = 0
  for (let i = 0; i < pixels.length; i += 4) {
    if (pixels[i + 3] < 128) continue
    const [hue, saturation, value] = hsv(pixels[i], pixels[i + 1], pixels[i + 2])
    const weight = saturation * value
    bins[Math.floor(hue / 15) % 24] += weight
    total += weight
  }
  if (total / (size * size) < 0.08) return null
  const hue = bins.indexOf(Math.max(...bins)) * 15 + 7.5
  const [best] = readTintHues().reduce((a, b) => (hueGap(hue, b[1]) < hueGap(hue, a[1]) ? b : a))
  return best
}

// By avatar URL. null: no match, so the record's own tint.
const matched = new Map<string, Tint | null>()
const STORAGE = 'mochi:avatar-tints'

try {
  for (const [url, tint] of Object.entries(JSON.parse(localStorage.getItem(STORAGE) ?? '{}')))
    matched.set(url, tint as Tint | null)
} catch {
  // No storage, e.g. a private window: tints are worked out again each visit.
}

function remember(url: string, tint: Tint | null) {
  matched.set(url, tint)
  try {
    localStorage.setItem(STORAGE, JSON.stringify(Object.fromEntries(matched)))
  } catch {
    // As above.
  }
}

/**
 * A client tile's tint: the palette tint closest to their avatar's colour, else their stable
 * tint from tintClass. Matched once per avatar, then remembered in this browser.
 */
export function useAvatarTint(id: number, avatarUrl: string | null): string {
  // Bumped when a match comes in, to render it; the tint itself is read from `matched`.
  const [, setMatches] = useState(0)

  useEffect(() => {
    if (!avatarUrl || matched.has(avatarUrl)) return
    let current = true
    // A failed load isn't remembered, so the next visit tries again.
    matchTint(avatarUrl).then(
      (found) => {
        remember(avatarUrl, found)
        if (current) setMatches((n) => n + 1)
      },
      () => {},
    )
    return () => {
      current = false
    }
  }, [avatarUrl])

  const tint = avatarUrl ? matched.get(avatarUrl) : undefined
  return tint ? `tint-${tint}` : tintClass(id)
}
