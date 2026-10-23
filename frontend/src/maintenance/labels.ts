import { contactKinds } from '../clients/contactKinds.ts'
import { daysBetween, formatDay, parseDate, todayISO } from '../format.ts'
import type { Month, Retainer } from './queries.ts'

/** "Oct", or "October" with long. */
export function monthName(period: string, long = false): string {
  return parseDate(period).toLocaleDateString('en-US', { month: long ? 'long' : 'short' })
}

/** 1st, 2nd, 3rd, 4th, …, 21st, 22nd, 23rd, 31st */
export function ordinal(day: number): string {
  const teen = day >= 11 && day <= 13
  const suffixes: Record<number, string> = { 1: 'st', 2: 'nd', 3: 'rd' }
  return `${day}${(!teen && suffixes[day % 10]) || 'th'}`
}

/** "Due today", "Due yesterday", "Due 2 days ago", "Due Sun" within the week, else "Due 25 Nov". */
export function dueLabel(dueOn: string, today = todayISO()): string {
  const days = daysBetween(today, dueOn)
  if (days === 0) return 'Due today'
  if (days === -1) return 'Due yesterday'
  if (days < 0 && days > -7) return `Due ${-days} days ago`
  if (days > 0 && days < 7) return `Due ${parseDate(dueOn).toLocaleDateString('en-US', { weekday: 'short' })}`
  return `Due ${formatDay(dueOn)}`
}

/** "Every 25th · ask on Discord", "Every 1st", plus how it ended or starts. */
export function scheduleText(retainer: Retainer): string {
  const parts = [`Every ${ordinal(retainer.due_day)}`]
  if (retainer.collection === 'ask') {
    parts[0] += retainer.ask_via ? ` · ask on ${contactKinds[retainer.ask_via.kind].label}` : ' · you ask'
  }
  if (retainer.ended_on && !retainer.active) parts.push(`ended ${formatDay(retainer.ended_on)}`)
  return parts.join(' · ')
}

export type Tone = '' | 'ok' | 'late' | 'due'

/** This month's status chip on the retainers list. */
export function monthChip(retainer: Retainer, today: string): { label: string; tone: Tone } {
  const month = retainer.this_month
  if (!month) {
    if (retainer.next_due_on) return { label: `From ${formatDay(retainer.next_due_on)}`, tone: '' }
    return { label: 'Ended', tone: '' }
  }
  return monthStatusChip(month, retainer, today)
}

export function monthStatusChip(month: Month, retainer: Retainer, today: string): { label: string; tone: Tone } {
  if (month.status === 'paid') return { label: `Paid ${formatDay(month.paid_on ?? month.due_on)}`, tone: 'ok' }
  if (month.status === 'overdue') return { label: `Overdue ${month.days_late}d`, tone: 'late' }
  // Upcoming, or due within the grace days. Auto transfers need nothing from you, so they
  // don't get the dark "act on this" chip.
  return { label: dueLabel(month.due_on, today), tone: retainer.collection === 'ask' ? 'due' : '' }
}

/** Unpaid "ask" months a payment can be recorded for: due and overdue ones, and the next one. */
export function openMonths(retainer: Retainer): Month[] {
  const all = [...retainer.overdue, ...retainer.months, ...(retainer.this_month ? [retainer.this_month] : [])]
  const unpaid = new Map(all.filter((m) => m.status !== 'paid').map((m) => [m.period, m]))
  return [...unpaid.values()].sort((a, b) => a.period.localeCompare(b.period))
}
