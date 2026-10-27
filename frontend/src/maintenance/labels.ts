import { contactKinds } from '../clients/contactKinds.ts'
import { daysBetween, formatDay, parseDate, todayISO } from '../format.ts'
import type { Month, Retainer } from './queries.ts'

/** "Oct", or "October" with long. */
export function monthName(period: string, long = false): string {
  return parseDate(period).toLocaleDateString('en-US', { month: long ? 'long' : 'short' })
}

/** The months a payment covers from `period`: "Jan–Mar 2027", or "Dec 2026–Feb 2027" across years. */
export function monthRange(period: string, months: number): string {
  const first = parseDate(period)
  const last = new Date(first.getFullYear(), first.getMonth() + months - 1, 1)
  const name = (date: Date) => date.toLocaleDateString('en-US', { month: 'short' })
  if (first.getFullYear() === last.getFullYear()) return `${name(first)}–${name(last)} ${last.getFullYear()}`
  return `${name(first)} ${first.getFullYear()}–${name(last)} ${last.getFullYear()}`
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

/**
 * "Every 25th · ask on Discord", "Every 1st", plus how it ended or starts. Without `contact`,
 * no "ask on", for rows that show the contact beside it.
 */
export function scheduleText(retainer: Retainer, { contact = true } = {}): string {
  const parts = [`Every ${ordinal(retainer.due_day)}`]
  if (contact && retainer.collection === 'ask') {
    parts[0] += retainer.ask_via ? ` · ask on ${contactKinds[retainer.ask_via.kind].label}` : ' · you ask'
  }
  if (retainer.ended_on && !retainer.active) parts.push(`ended ${formatDay(retainer.ended_on)}`)
  return parts.join(' · ')
}

export type Tone = '' | 'ok' | 'late' | 'due'

/** This month's status chip on the retainers list. */
export function monthChip(retainer: Retainer, today: string): { label: string; tone: Tone } {
  if (retainer.paused_on) return { label: 'Paused', tone: '' }
  const month = retainer.this_month
  if (!month) {
    const waived = waiverLabel(retainer, `${today.slice(0, 8)}01`)
    if (waived) return { label: waived, tone: '' }
    if (retainer.next_due_on) return { label: `From ${formatDay(retainer.next_due_on)}`, tone: '' }
    return { label: 'Ended', tone: '' }
  }
  return monthStatusChip(month, retainer, today)
}

/** "Waived" or "Given up" for a month that isn't billed for either reason, else null. */
function waiverLabel(retainer: Retainer, period: string): string | null {
  const waiver = retainer.waivers.find((w) => w.period === period)
  if (!waiver) return null
  return waiver.kind === 'given_up' ? 'Given up' : 'Waived'
}

/** A month's due date: `dueDay`, or the month's last day when it's shorter. */
function dueOn(period: string, dueDay: number): string {
  const first = parseDate(period)
  const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  return `${period.slice(0, 8)}${String(Math.min(dueDay, last)).padStart(2, '0')}`
}

/** The chip for the calendar's month on the retainers list: its status, or why it isn't billed. */
export function periodChip(
  retainer: Retainer,
  month: Month | undefined,
  period: string,
  today: string,
): { label: string; tone: Tone } {
  if (period === `${today.slice(0, 8)}01`) return monthChip(retainer, today)
  if (month) return monthStatusChip(month, retainer, today)
  const due = dueOn(period, retainer.due_day)
  if (retainer.ended_on && due > retainer.ended_on) return { label: 'Ended', tone: '' }
  if (due < retainer.started_on) return { label: `From ${formatDay(retainer.started_on)}`, tone: '' }
  if (period < retainer.tracked_from) return { label: 'Settled', tone: '' }
  const waived = waiverLabel(retainer, period)
  if (waived) return { label: waived, tone: '' }
  return { label: 'Paused', tone: '' }
}

export function monthStatusChip(month: Month, retainer: Retainer, today: string): { label: string; tone: Tone } {
  if (month.status === 'paid') return { label: `Paid ${formatDay(month.paid_on ?? month.due_on)}`, tone: 'ok' }
  if (month.status === 'overdue') return { label: `Overdue ${month.days_late}d`, tone: 'late' }
  if (month.status === 'unpaid') return { label: 'Unpaid', tone: '' }
  // Upcoming, or due within the grace days. Auto transfers need nothing from you, so they
  // don't get the dark "act on this" chip.
  return { label: dueLabel(month.due_on, today), tone: retainer.collection === 'ask' ? 'due' : '' }
}

/** Every month the API sent for a retainer: overdue ones, the recent ones and this month. */
function knownMonths(retainer: Retainer): Month[] {
  return [...retainer.overdue, ...retainer.months, ...(retainer.this_month ? [retainer.this_month] : [])]
}

/** One of those months by its first day, e.g. for a reminder's Record payment link. */
export function findMonth(retainer: Retainer, period: string): Month | undefined {
  return knownMonths(retainer).find((m) => m.period === period)
}

/** Unpaid "ask" months a payment can be recorded for: due and overdue ones, and the next one. */
export function openMonths(retainer: Retainer): Month[] {
  const unpaid = new Map(knownMonths(retainer).filter((m) => m.status !== 'paid').map((m) => [m.period, m]))
  return [...unpaid.values()].sort((a, b) => a.period.localeCompare(b.period))
}
