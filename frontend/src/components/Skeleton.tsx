/** A placeholder tile: its span classes (none in a card grid) and about how tall the real one is. */
export type Bone = { span?: string; height: number }

type Props = {
  /** The page's tiles in order, so the layout is in place before the data. */
  tiles: Bone[]
  /** Said to screen readers, e.g. "Loading projects". */
  label: string
  /** The grid the real tiles sit in. */
  className?: string
}

/** A page's tiles as pulsing outlines while its data loads: a label, a figure and a line each. */
export function Skeleton({ tiles, label, className = 'bento' }: Props) {
  return (
    <div className={className} role="status" aria-label={label}>
      {tiles.map((tile, i) => (
        <div key={i} className={`tile skeleton ${tile.span ?? ''}`} style={{ minHeight: tile.height }} aria-hidden="true">
          <i className="skeleton-bar" />
          <i className="skeleton-bar big" />
          <i className="skeleton-bar wide" />
        </div>
      ))}
    </div>
  )
}
