import { daysBetween, plural, todayISO } from '../format.ts'
import type { Project, Status } from './queries.ts'

export const statusLabels: Record<Status, string> = {
  in_progress: 'In progress',
  final_payment_due: 'Final payment due',
  done: 'Done',
}

export type Tone = '' | 'good' | 'warn'

/** Due dates this close get the warning colour. */
const SOON_DAYS = 14

/** Days left until the due date; negative once overdue. Null without a due date. */
export function daysLeft(project: Project): number | null {
  return project.due_on ? daysBetween(todayISO(), project.due_on) : null
}

/** "23 days left", "Due in 8 days", "3 days overdue", … */
export function dueText(left: number): string {
  if (left < 0) return `${plural(-left, 'day')} overdue`
  if (left === 0) return 'Due today'
  if (left <= SOON_DAYS) return `Due in ${plural(left, 'day')}`
  return `${plural(left, 'day')} left`
}

/** The chip on a project card: schedule while in progress, otherwise the status. */
export function scheduleChip(project: Project): { label: string; tone: Tone } {
  if (project.status === 'done') return { label: 'Done', tone: 'good' }
  if (project.status === 'final_payment_due') return { label: 'Final payment due', tone: 'warn' }
  const left = daysLeft(project)
  if (left === null) return { label: 'No due date', tone: '' }
  return { label: dueText(left), tone: left <= SOON_DAYS ? 'warn' : '' }
}

/**
 * How far along the schedule is, 0–100. Delivered projects are full; projects without a
 * due date have no progress (null) and show an open, dashed track instead.
 */
export function elapsedPercent(project: Project): number | null {
  if (project.delivered_on) return 100
  if (!project.due_on) return null
  const span = daysBetween(project.started_on, project.due_on)
  const gone = daysBetween(project.started_on, todayISO())
  if (span <= 0) return gone >= 0 ? 100 : 0
  return Math.min(100, Math.max(0, Math.round((gone / span) * 100)))
}

/** Days since the start, for projects without a due date. */
export function daysIn(project: Project): number {
  return Math.max(0, daysBetween(project.started_on, todayISO()))
}
