const ntd = new Intl.NumberFormat('en-US')

/** Whole NTD amounts, e.g. NT$12,000. */
export function formatNTD(amount: number): string {
  return `NT$${ntd.format(amount)}`
}

/** Up to two initials, e.g. "Northwind Coffee" -> "NC". */
export function initials(name: string): string {
  const words = name.replace(/^@/, '').split(/[\s._-]+/).filter(Boolean)
  return words
    .slice(0, 2)
    .map((w) => w[0].toUpperCase())
    .join('')
}

/** "March 2025" */
export function formatMonth(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

/** Whole numbers with separators, e.g. 12,000. For amounts shown after a separate NT$ label. */
export function formatNumber(amount: number): string {
  return ntd.format(amount)
}

/** "1 addition", "2 additions" */
export function plural(count: number, word: string): string {
  return `${count} ${count === 1 ? word : `${word}s`}`
}

/** A local Date for an ISO date like 2026-10-23 (new Date() would read it as UTC). */
export function parseDate(iso: string): Date {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

/** A local Date as an ISO date like 2026-10-23. */
export function isoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

/** Today as an ISO date, in local time. */
export function todayISO(): string {
  return isoDate(new Date())
}

/** Whole days from one ISO date to another; negative when `to` is earlier. */
export function daysBetween(from: string, to: string): number {
  return Math.round((parseDate(to).getTime() - parseDate(from).getTime()) / 86_400_000)
}

/** "4 Aug", or "4 Aug 2026" with year, or "Tue 4 Aug" with weekday. */
export function formatDay(iso: string, options: { year?: boolean; weekday?: boolean } = {}): string {
  const date = parseDate(iso)
  const part = (format: Intl.DateTimeFormatOptions) => date.toLocaleDateString('en-US', format)
  return [
    options.weekday && part({ weekday: 'short' }),
    date.getDate(),
    part({ month: 'short' }),
    options.year && date.getFullYear(),
  ]
    .filter(Boolean)
    .join(' ')
}

/** "just now", "5 min ago", "2 h ago", "3 days ago" for an ISO timestamp. */
export function timeAgo(iso: string, now = Date.now()): string {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60_000))
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  return `${plural(Math.round(hours / 24), 'day')} ago`
}
