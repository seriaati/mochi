import { useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react'
import { formatNTD, formatNumber } from '../format.ts'
import type { Source } from './queries.ts'
import { sourceColor, sourceLabels, type Bucket, type Split } from './slice.ts'

const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })

/** A round step that splits `max` into about four gridlines. */
function niceStep(max: number): number {
  const raw = max / 4
  const power = 10 ** Math.floor(Math.log10(raw))
  const fraction = raw / power
  return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power
}

/** The y scale for values up to `max`: its top and the gridlines' values, from 0. */
function scale(max: number): { top: number; ticks: number[] } {
  const step = niceStep(Math.max(max, 1000))
  const top = step * Math.max(Math.ceil(max / step), 1)
  const ticks = Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step)
  return { top, ticks }
}

/** Gridlines with their amounts: in full under 10,000, compact (10K) on an axis that reaches it. */
function Grid({ top, ticks }: { top: number; ticks: number[] }) {
  return (
    <div className="st-grid" aria-hidden="true">
      {ticks.map((tick) => (
        <div key={tick} className="st-gridline" style={{ bottom: `${(tick / top) * 100}%` }}>
          <span>{top < 10_000 ? formatNumber(tick) : compact.format(tick)}</span>
        </div>
      ))}
    </div>
  )
}

/** Labels under the columns, thinned out when there are too many to fit. */
function XLabels({ labels }: { labels: string[] }) {
  const every = Math.ceil(labels.length / 12)
  return (
    <div className={`st-xlabels${labels.length > 6 ? ' dense' : ''}`} style={{ gridTemplateColumns: `repeat(${labels.length}, minmax(0, 1fr))` }} aria-hidden="true">
      {labels.map((label, i) => (
        <span key={i}>{i % every === 0 ? label : ''}</span>
      ))}
    </div>
  )
}

export type TipRow = { key: string; value: string; label: string; swatch?: string; line?: boolean }

/** The hover readout, beside the column or point at `at` (0–1 across the plot). */
function Tip({ at, title, rows }: { at: number; title: string; rows: TipRow[] }) {
  return (
    <div className={at > 0.5 ? 'st-tip end' : 'st-tip'} style={{ left: `${at * 100}%` }} aria-hidden="true">
      <p className="st-tip-title">{title}</p>
      {rows.map((row) => (
        <p key={row.key}>
          {row.swatch && <i className={row.line ? 'line' : undefined} style={{ background: row.swatch }} />}
          <b>{row.value}</b>
          <span>{row.label}</span>
        </p>
      ))}
    </div>
  )
}

/** Names each series by its mark: a square for bars, a short line for lines. */
export function Legend({ items }: { items: { key: string; label: string; color: string; line?: boolean }[] }) {
  return (
    <ul className="st-legend">
      {items.map((item) => (
        <li key={item.key}>
          <i className={item.line ? 'line' : undefined} style={{ background: item.color }} />
          {item.label}
        </li>
      ))}
    </ul>
  )
}

type ColumnProps = { buckets: Bucket[]; splits: Split[]; sources: Source[]; label: string }

/** Money per month (or year), each column stacked by source, projects at the bottom. */
export function ColumnChart({ buckets, splits, sources, label }: ColumnProps) {
  const [active, setActive] = useState<number | null>(null)
  const totals = splits.map((split) => sum(sources, split))
  const { top, ticks } = scale(Math.max(...totals))
  const count = buckets.length

  const describe = (i: number) =>
    `${buckets[i].title}: ${formatNTD(totals[i])}` +
    (sources.length > 1 ? ` (${sources.map((s) => `${sourceLabels[s]} ${formatNTD(splits[i][s])}`).join(', ')})` : '')

  return (
    <div className="st-chart">
      <div className="st-plot">
        <Grid top={top} ticks={ticks} />
        <div className="st-columns" role="list" aria-label={label} style={{ gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))` }}>
          {buckets.map((bucket, i) => (
            <div
              key={bucket.title}
              className="st-col"
              role="listitem"
              tabIndex={0}
              aria-label={describe(i)}
              onPointerEnter={() => setActive(i)}
              onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)}
              onBlur={() => setActive(null)}
            >
              <div className="st-stack" style={{ height: `${(totals[i] / top) * 100}%` }}>
                {[...sources].reverse().map(
                  (source) =>
                    splits[i][source] > 0 && (
                      <i key={source} style={{ flexGrow: splits[i][source], background: sourceColor(source) }} />
                    ),
                )}
              </div>
            </div>
          ))}
        </div>
        {active !== null && (
          <Tip
            at={(active + 0.5) / count}
            title={buckets[active].title}
            rows={[
              ...(sources.length > 1
                ? sources.map((source) => ({
                    key: source,
                    value: formatNTD(splits[active][source]),
                    label: sourceLabels[source],
                    swatch: sourceColor(source),
                    line: true,
                  }))
                : []),
              { key: 'total', value: formatNTD(totals[active]), label: sources.length > 1 ? 'Total' : 'Received' },
            ]}
          />
        )}
      </div>
      <XLabels labels={buckets.map((b) => b.label)} />
    </div>
  )
}

const sum = (sources: Source[], split: Split) => sources.reduce((acc, s) => acc + split[s], 0)

type Line = { key: string; label: string; color: string; values: number[] }

type LineProps = {
  buckets: Bucket[]
  /** Running totals at the end of each bucket; the first line is the one the chart is about. */
  lines: Line[]
  label: string
  /** Extra readout rows for the bucket under the pointer, e.g. the difference. */
  extra?: (i: number) => TipRow[]
}

/** Running totals as lines, with a crosshair that snaps to the month under the pointer. */
export function LineChart({ buckets, lines, label, extra }: LineProps) {
  const [active, setActive] = useState<number | null>(null)
  const { top, ticks } = scale(Math.max(...lines.flatMap((l) => l.values)))
  const count = buckets.length
  // x of each bucket's middle, 0–100, under its label.
  const x = (i: number) => ((i + 0.5) / count) * 100
  const y = (value: number) => 100 - (value / top) * 100
  const path = (values: number[]) => values.map((v, i) => `${i ? 'L' : 'M'}${x(i)} ${y(v)}`).join(' ')
  const [main] = lines

  function point(event: PointerEvent<HTMLDivElement>) {
    const rect = event.currentTarget.getBoundingClientRect()
    const at = ((event.clientX - rect.left) / rect.width) * count
    setActive(Math.min(Math.max(Math.floor(at), 0), count - 1))
  }

  function key(event: KeyboardEvent<HTMLDivElement>) {
    const step = { ArrowLeft: -1, ArrowRight: 1 }[event.key]
    if (step === undefined) return
    event.preventDefault()
    setActive((i) => Math.min(Math.max((i ?? count - 1) + step, 0), count - 1))
  }

  return (
    <div className="st-chart">
      <div
        className="st-plot st-line-plot"
        role="img"
        tabIndex={0}
        aria-label={label}
        onPointerMove={point}
        onPointerLeave={() => setActive(null)}
        onFocus={() => setActive(count - 1)}
        onBlur={() => setActive(null)}
        onKeyDown={key}
      >
        <Grid top={top} ticks={ticks} />
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          <path className="st-area" d={`${path(main.values)} L${x(count - 1)} 100 L${x(0)} 100 Z`} style={{ fill: main.color }} />
          {[...lines].reverse().map((line) => (
            <path key={line.key} className="st-line" d={path(line.values)} style={{ stroke: line.color }} />
          ))}
        </svg>
        {active !== null && <i className="st-crosshair" style={{ left: `${x(active)}%` }} aria-hidden="true" />}
        {lines.map((line) => {
          const i = active ?? count - 1
          return (
            <i
              key={line.key}
              className="st-dot"
              style={{ left: `${x(i)}%`, bottom: `${100 - y(line.values[i])}%`, background: line.color }}
              aria-hidden="true"
            />
          )
        })}
        {active !== null && (
          <Tip
            at={x(active) / 100}
            title={`By the end of ${buckets[active].title}`}
            rows={[
              ...lines.map((line) => ({
                key: line.key,
                value: formatNTD(line.values[active]),
                label: line.label,
                swatch: line.color,
                line: true,
              })),
              ...(extra?.(active) ?? []),
            ]}
          />
        )}
      </div>
      <XLabels labels={buckets.map((b) => b.label)} />
    </div>
  )
}

/** A tile's body when there's nothing to chart. */
export function NoData({ children }: { children: ReactNode }) {
  return <p className="empty-note st-nodata">{children}</p>
}
