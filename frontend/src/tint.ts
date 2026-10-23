/** Pastel tints in mockup order; the matching .tint-* classes live in index.css. */
const tints = ['peach', 'blue', 'lavender', 'yellow', 'sage', 'teal'] as const

/** A stable tint class for a record, e.g. a client card. */
export function tintClass(id: number): string {
  return `tint-${tints[id % tints.length]}`
}
