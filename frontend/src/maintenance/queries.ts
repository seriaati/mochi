import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api.ts'
import type { Contact, DiscordProfile } from '../clients/queries.ts'

/** auto_transfer: counts as paid on the due date. ask: paid once a payment is recorded. */
export type Collection = 'auto_transfer' | 'ask'

/**
 * upcoming: the due date is still ahead. due: an unpaid "ask" month from its due date through
 * the 2 grace days after it. overdue: an unpaid "ask" month past the grace days. unpaid: an
 * "ask" month left unpaid when the retainer was paused; never overdue or reminded.
 */
export type MonthStatus = 'paid' | 'upcoming' | 'due' | 'overdue' | 'unpaid'

export type RetainerInput = {
  client_id: number
  /** The project it's for; may be another client's, e.g. a bot several clients pay for. */
  project_id: number | null
  /** NTD per month. */
  amount: number
  /** 1–31; shorter months fall due on their last day. */
  due_day: number
  collection: Collection
  /** The client contact to ask on; "ask" retainers only. */
  ask_via_id: number | null
  started_on: string
  ended_on: string | null
  /** First tracked month (its first day); earlier months count as settled. */
  tracked_from: string
}

/** One billed month of a retainer, as of today. */
export type Month = {
  /** First day of the month. */
  period: string
  due_on: string
  /** The fee, or this month's share of the payment for a paid "ask" month. */
  amount: number
  status: MonthStatus
  /** Auto transfers count as paid on the due date. */
  paid_on: string | null
  /** The recorded payment covering it, "ask" retainers only. */
  payment: RetainerPayment | null
  /** Due, overdue or unpaid: days since the due date. Paid "ask" month: days paid after it. */
  days_late: number
  /** Overdue, or paid more than the 2 grace days after the due date. */
  late: boolean
}

/** avatar_url: the client's synced Discord avatar, if any. */
export type RetainerClient = { id: number; name: string; avatar_url: string | null }

export type Retainer = RetainerInput & {
  id: number
  client: RetainerClient
  project: { id: number; name: string } | null
  ask_via: Contact | null
  /** Started, not ended and not paused, as of today. */
  active: boolean
  /** When it was paused, while it is. */
  paused_on: string | null
  /** Null when this month isn't billed. */
  this_month: Month | null
  /** The next month due today or later, past any "ask" months paid ahead; null once ended or while paused. */
  next_due_on: string | null
  /** The last few billed months up to the next one due, oldest first. */
  months: Month[]
  /** Oldest first. */
  overdue: Month[]
  /** NTD received all time. */
  received: number
}

/** period: the first month paid for. months: how many in a row, when paid ahead. amount: for all of them. */
export type RetainerPaymentInput = { period: string; months: number; amount: number; paid_on: string }

export type RetainerPayment = RetainerPaymentInput & { id: number; retainer_id: number }

export type Overdue = {
  retainer_id: number
  client: RetainerClient
  period: string
  due_on: string
  amount: number
  days: number
  last_reminded_on: string | null
}

/** A client's next combined reminder. */
export type NextReminder = {
  client: RetainerClient
  /** The months it asks for, oldest first. */
  periods: string[]
  /** The oldest of those months' due dates. */
  due_on: string
  /** All of them together. */
  amount: number
  /** 09:00 on the slot's date, ISO with the saved timezone's offset. */
  at: string
  /** Its time has passed; the scheduler sends it within a minute once reminders are on. */
  pending: boolean
  last_reminded_on: string | null
}

export type CalendarDay = {
  day: string
  /** overdue if any entry is, else upcoming if any is, else paid. */
  status: MonthStatus
  entries: { retainer_id: number; client: RetainerClient; amount: number; status: MonthStatus }[]
}

export type Maintenance = {
  today: string
  /** The calendar's month, first day. */
  month: string
  active_count: number
  monthly_total: number
  /** Overdue in the calendar's month first, then active ones, then by client name. */
  retainers: Retainer[]
  /** Each retainer's calendar month, by retainer ID; only those billed then. */
  months: Record<number, Month>
  /** Oldest first. */
  overdue: Overdue[]
  next_reminder: NextReminder | null
  /** This month's fees, by the month they're for. */
  collected: { period: string; received: number; expected: number; paid: number; count: number }
  automatic: { amount: number; clients: number }
  /** Only days with something due. */
  calendar: CalendarDay[]
  reminders: {
    enabled: boolean
    mention_user_id: string | null
    /** Your synced Discord profile, with mention_user_id. */
    mention: DiscordProfile | null
    timezone: string
    time: string
    repeat_days: number
  }
}

const keys = {
  all: ['maintenance'] as const,
  overview: (month: string | null) => ['maintenance', 'overview', month] as const,
  ofClient: (clientId: number) => ['maintenance', 'retainers', { clientId }] as const,
  ofProject: (projectId: number) => ['maintenance', 'retainers', { projectId }] as const,
}

/** The Maintenance page. month is YYYY-MM for the calendar, or null for this month. */
export function useMaintenance(month: string | null) {
  return useQuery({
    queryKey: keys.overview(month),
    queryFn: () => api.get<Maintenance>(month ? `/maintenance?month=${month}` : '/maintenance'),
    placeholderData: keepPreviousData,
  })
}

export function useClientRetainers(clientId: number) {
  return useQuery({
    queryKey: keys.ofClient(clientId),
    queryFn: () => api.get<Retainer[]>(`/retainers?client_id=${clientId}`),
  })
}

export function useProjectRetainers(projectId: number) {
  return useQuery({
    queryKey: keys.ofProject(projectId),
    queryFn: () => api.get<Retainer[]>(`/retainers?project_id=${projectId}`),
  })
}

/** Retainer changes refetch all maintenance data and the clients' fees and flags. */
function useMaintenanceMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
      ]),
  })
}

export function useSaveRetainer(id?: number) {
  return useMaintenanceMutation((input: RetainerInput) =>
    id === undefined
      ? api.post<Retainer>('/retainers', input)
      : api.put<Retainer>(`/retainers/${id}`, input),
  )
}

/** Stops billing from today, and reminders for what's left unpaid, until resumed. */
export function usePauseRetainer(id: number) {
  return useMaintenanceMutation(() => api.post<Retainer>(`/retainers/${id}/pause`, {}))
}

/** Bills again from today; months due while paused stay unbilled. */
export function useResumeRetainer(id: number) {
  return useMaintenanceMutation(() => api.post<Retainer>(`/retainers/${id}/resume`, {}))
}

export function useDeleteRetainer() {
  return useMaintenanceMutation((id: number) => api.delete(`/retainers/${id}`))
}

export function useRecordRetainerPayment(retainerId: number) {
  return useMaintenanceMutation((input: RetainerPaymentInput) =>
    api.post<RetainerPayment>(`/retainers/${retainerId}/payments`, input),
  )
}

export function useDeleteRetainerPayment(retainerId: number) {
  return useMaintenanceMutation((paymentId: number) =>
    api.delete(`/retainers/${retainerId}/payments/${paymentId}`),
  )
}

/** Reminder sends only move the next reminder and "last reminded", so only maintenance refetches. */
export function useSendTest() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ content: string }>('/maintenance/reminders/test', {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all }),
  })
}
