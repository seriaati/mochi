import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api.ts'

/** in_progress: not delivered. final_payment_due: delivered, not fully paid. done: both. */
export type Status = 'in_progress' | 'final_payment_due' | 'done'

/** Money figures the API derives for a project (its own price only) or an addition. All NTD. */
export type Billing = {
  expected_deposit: number
  expected_final: number
  paid: number
  outstanding: number
  /** What's left of the deposit. */
  deposit_due: number
  /** What's left of the final payment. deposit_due + final_due = outstanding. */
  final_due: number
  status: Status
}

export type ProjectInput = {
  client_id: number
  name: string
  description: string | null
  price: number
  deposit_percent: number
  /** ISO dates, e.g. 2026-10-23. */
  started_on: string
  due_on: string | null
  delivered_on: string | null
}

export type AdditionInput = {
  name: string
  description: string | null
  price: number
  /** 0 means a single payment. */
  deposit_percent: number
  agreed_on: string
  delivered_on: string | null
}

export type Addition = AdditionInput & Billing & { id: number; project_id: number }

export type PaymentInput = {
  /** null pays the project itself. */
  addition_id: number | null
  amount: number
  paid_on: string
  note: string | null
}

/** deposit / final: where the payment falls against the expected deposit. */
export type Payment = PaymentInput & { id: number; kind: 'deposit' | 'final' | 'payment' }

export type Project = ProjectInput &
  Billing & {
    id: number
    created_at: string
    /** avatar_url: the client's synced Discord avatar, if any. */
    client: { id: number; name: string; contact_person: string | null; avatar_url: string | null }
    /** Newest agreed first. */
    additions: Addition[]
    /** For the project and its additions, oldest first. */
    payments: Payment[]
    additions_total: number
    /** price + additions_total */
    total: number
    total_paid: number
    total_outstanding: number
  }

const keys = {
  all: ['projects'] as const,
  one: (id: number) => ['projects', id] as const,
  ofClient: (clientId: number) => ['projects', { clientId }] as const,
}

export function useProjects() {
  return useQuery({ queryKey: keys.all, queryFn: () => api.get<Project[]>('/projects') })
}

export function useClientProjects(clientId: number) {
  return useQuery({
    queryKey: keys.ofClient(clientId),
    queryFn: () => api.get<Project[]>(`/projects?client_id=${clientId}`),
  })
}

export function useProject(id: number) {
  return useQuery({ queryKey: keys.one(id), queryFn: () => api.get<Project>(`/projects/${id}`) })
}

/**
 * Mutations refetch every project query, since figures show on lists and detail alike.
 * Pass clientStats when the change moves a client's project count or lifetime billed.
 */
function useProjectsMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  { clientStats }: { clientStats: boolean },
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        clientStats && queryClient.invalidateQueries({ queryKey: ['clients'] }),
      ]),
  })
}

export function useSaveProject(id?: number) {
  return useProjectsMutation(
    (input: ProjectInput) =>
      id === undefined
        ? api.post<Project>('/projects', input)
        : api.put<Project>(`/projects/${id}`, input),
    { clientStats: true },
  )
}

/** Drops the deleted project's own query rather than refetching it into a 404. */
export function useDeleteProject() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.delete(`/projects/${id}`),
    onSuccess: (_, id) => {
      queryClient.removeQueries({ queryKey: keys.one(id), exact: true })
      return Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
      ])
    },
  })
}

export function useSaveAddition(projectId: number, additionId?: number) {
  const base = `/projects/${projectId}/additions`
  return useProjectsMutation(
    (input: AdditionInput) =>
      additionId === undefined
        ? api.post<Addition>(base, input)
        : api.put<Addition>(`${base}/${additionId}`, input),
    { clientStats: true },
  )
}

export function useDeleteAddition(projectId: number) {
  return useProjectsMutation(
    (additionId: number) => api.delete(`/projects/${projectId}/additions/${additionId}`),
    { clientStats: true },
  )
}

/** Records a payment, or edits one (amount, date, note, or which target it's for). */
export function useSavePayment(projectId: number, paymentId?: number) {
  const base = `/projects/${projectId}/payments`
  return useProjectsMutation(
    (input: PaymentInput) =>
      paymentId === undefined
        ? api.post<Payment>(base, input)
        : api.put<Payment>(`${base}/${paymentId}`, input),
    { clientStats: false },
  )
}

export function useDeletePayment(projectId: number) {
  return useProjectsMutation(
    (paymentId: number) => api.delete(`/projects/${projectId}/payments/${paymentId}`),
    { clientStats: false },
  )
}

/** The full PUT body for a project, e.g. to change one field like delivered_on. */
export function projectInput(project: Project): ProjectInput {
  const { client_id, name, description, price, deposit_percent, started_on, due_on, delivered_on } =
    project
  return { client_id, name, description, price, deposit_percent, started_on, due_on, delivered_on }
}

export function additionInput(addition: Addition): AdditionInput {
  const { name, description, price, deposit_percent, agreed_on, delivered_on } = addition
  return { name, description, price, deposit_percent, agreed_on, delivered_on }
}
