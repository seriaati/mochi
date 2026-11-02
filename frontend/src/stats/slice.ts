import { formatDay, formatMonth } from '../format.ts'
import type { IncomeEntry, Source } from './queries.ts'

/** The stretch of time the page looks at: the last 12 months, a calendar year, or all time. */
export type Period = 'last12' | 'all' | `${number}`

export type Range = {
  /** ISO dates, inclusive. */
  first: string
  last: string
  /** Each month in it as YYYY-MM, oldest first. */
  months: string[]
  /** "Last 12 months", "2026", "All time" */
  label: string
  /** "in the last 12 months", "in 2026", "so far" */
  phrase: string
  /** The same stretch a year earlier, to compare with; null for all time. */
  previous: {
    first: string
    last: string
    /** "Year before", "2025" */
    label: string
    /** "in the year before", "in 2025 by 23 Oct", "in 2025" */
    phrase: string
  } | null
}

export const SOURCES: Source[] = ['project', 'addition', 'retainer']

export const sourceLabels: Record<Source, string> = {
  project: 'Projects',
  addition: 'Additions',
  retainer: 'Retainers',
}

/** A source's series colour on charts, e.g. var(--chart-projects). */
export const sourceColor = (source: Source) => `var(--chart-${source}s)`

/** A YYYY-MM month `count` months later (earlier when negative). */
export function addMonths(month: string, count: number): string {
  const index = Number(month.slice(0, 4)) * 12 + Number(month.slice(5, 7)) - 1 + count
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}`
}

/** Every YYYY-MM month from `first` to `last`, inclusive. */
function monthsFrom(first: string, last: string): string[] {
  const months = []
  for (let month = first; month <= last; month = addMonths(month, 1)) months.push(month)
  return months
}

/** The same ISO date a year earlier; 29 February becomes the 28th. */
export function yearBefore(iso: string): string {
  const day = iso.slice(5) === '02-29' ? '02-28' : iso.slice(5)
  return `${Number(iso.slice(0, 4)) - 1}-${day}`
}

/** The dates a period covers, up to today. `earliest` is where all time starts. */
export function rangeFor(period: Period, today: string, earliest: string): Range {
  const thisMonth = today.slice(0, 7)
  if (period === 'all') {
    const first = `${earliest.slice(0, 7)}-01`
    const months = monthsFrom(first.slice(0, 7), thisMonth)
    return { first, last: today, months, label: 'All time', phrase: 'so far', previous: null }
  }
  if (period === 'last12') {
    const start = addMonths(thisMonth, -11)
    return {
      first: `${start}-01`,
      last: today,
      months: monthsFrom(start, thisMonth),
      label: 'Last 12 months',
      phrase: 'in the last 12 months',
      previous: {
        first: `${addMonths(start, -12)}-01`,
        last: yearBefore(today),
        label: 'Year before',
        phrase: 'in the year before',
      },
    }
  }
  const last = `${period}-12-31` < today ? `${period}-12-31` : today
  const before = String(Number(period) - 1)
  return {
    first: `${period}-01-01`,
    last,
    months: monthsFrom(`${period}-01`, last.slice(0, 7)),
    label: period,
    phrase: `in ${period}`,
    previous: {
      first: `${before}-01-01`,
      last: yearBefore(last),
      label: before,
      // A year still going compares with the year before up to the same date.
      phrase: last === today ? `in ${before} by ${formatDay(yearBefore(last))}` : `in ${before}`,
    },
  }
}

export const within = (entry: IncomeEntry, first: string, last: string) =>
  entry.paid_on >= first && entry.paid_on <= last

export const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)

export const mean = (values: number[]) => (values.length ? sum(values) / values.length : 0)

export function median(values: number[]): number {
  if (!values.length) return 0
  const sorted = [...values].sort((a, b) => a - b)
  const middle = Math.floor(sorted.length / 2)
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2
}

/** Whole percent of a part, or null when there's no whole. */
export const percent = (part: number, whole: number) => (whole ? Math.round((part / whole) * 100) : null)

export type Split = Record<Source, number>

export const emptySplit = (): Split => ({ project: 0, addition: 0, retainer: 0 })

/** Money received per month (YYYY-MM), by source. Months without any are missing. */
export function byMonth(entries: IncomeEntry[]): Map<string, Split> {
  const months = new Map<string, Split>()
  for (const entry of entries) {
    const key = entry.paid_on.slice(0, 7)
    const split = months.get(key) ?? emptySplit()
    split[entry.source] += entry.amount
    months.set(key, split)
  }
  return months
}

/** A column on a chart: a month, or a year when there are too many months to show. */
export type Bucket = { label: string; title: string; months: string[] }

/** A column per month for up to two years, else per year. */
export function bucketsFor(months: string[]): Bucket[] {
  if (months.length <= 24) {
    return months.map((month) => ({
      label: formatMonth(`${month}-01`).slice(0, 3),
      title: formatMonth(`${month}-01`),
      months: [month],
    }))
  }
  const years = [...new Set(months.map((m) => m.slice(0, 4)))]
  return years.map((year) => ({ label: year, title: year, months: months.filter((m) => m.startsWith(year)) }))
}

/** Adds up a bucket's months. */
export function splitOf(bucket: Bucket, months: Map<string, Split>): Split {
  const split = emptySplit()
  for (const month of bucket.months) {
    const found = months.get(month)
    if (found) for (const source of SOURCES) split[source] += found[source]
  }
  return split
}
