import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api.ts'

export type ContactKind = 'discord' | 'line' | 'email' | 'other'

export type ContactInput = {
  kind: ContactKind
  value: string
  /** Discord snowflake, kept as a string because it doesn't fit in a JS number. */
  discord_user_id: string | null
}

/**
 * A Discord user's synced profile. pending: not looked up yet. off: no bot token, so nothing
 * syncs. error: the last lookup failed; the other fields are from the last good one, if any.
 */
export type DiscordProfile = {
  status: 'ok' | 'not_found' | 'error' | 'pending' | 'off'
  /** The last lookup, whatever its result. */
  synced_at: string | null
  username: string | null
  /** Their display name, else the username. */
  display_name: string | null
  /** Their avatar, or Discord's default one. */
  avatar_url: string | null
}

export type Contact = ContactInput & {
  id: number
  /** Discord contacts with a user ID; otherwise null. */
  discord_profile: DiscordProfile | null
}

export type ClientInput = {
  name: string
  contact_person: string | null
  notes: string | null
}

export type Client = ClientInput & {
  id: number
  created_at: string
  contacts: Contact[]
  /** From the primary Discord contact (the first one synced); null without one. */
  avatar_url: string | null
  discord_name: string | null
  project_count: number
  /** NTD: project prices plus their additions. */
  lifetime_billed: number
  /** NTD: sum of active retainers. */
  monthly_maintenance: number
  /** The card's flag: an "ask" month overdue, this month's "ask" fee still to come, or auto-pay. */
  maintenance_flag: 'overdue' | 'due' | 'auto' | null
  /** With the "due" flag. */
  maintenance_due_on: string | null
}

const keys = {
  all: ['clients'] as const,
  one: (id: number) => ['clients', id] as const,
}

export function useClients() {
  return useQuery({ queryKey: keys.all, queryFn: () => api.get<Client[]>('/clients') })
}

export function useClient(id: number) {
  return useQuery({ queryKey: keys.one(id), queryFn: () => api.get<Client>(`/clients/${id}`) })
}

/**
 * Mutations refetch every client query, since contacts and stats show on the list too,
 * maintenance, which shows the contact each retainer asks on, and projects, which show the
 * client's Discord avatar.
 */
function useClientsMutation<TArgs, TResult>(fn: (args: TArgs) => Promise<TResult>) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: ['maintenance'] }),
        queryClient.invalidateQueries({ queryKey: ['projects'] }),
      ]),
  })
}

export function useSaveClient(id?: number) {
  return useClientsMutation((input: ClientInput) =>
    id === undefined ? api.post<Client>('/clients', input) : api.put<Client>(`/clients/${id}`, input),
  )
}

export function useDeleteClient(id: number) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.delete(`/clients/${id}`),
    // Only the list: refetching the deleted client itself would 404 before we navigate away.
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.all, exact: true }),
  })
}

export function useSaveContact(clientId: number, contactId?: number) {
  const base = `/clients/${clientId}/contacts`
  return useClientsMutation((input: ContactInput) =>
    contactId === undefined
      ? api.post<Contact>(base, input)
      : api.put<Contact>(`${base}/${contactId}`, input),
  )
}

export function useDeleteContact(clientId: number) {
  return useClientsMutation((contactId: number) =>
    api.delete(`/clients/${clientId}/contacts/${contactId}`),
  )
}

/** Looks the client's Discord profiles up now, however recently they were synced. */
export function useSyncDiscord(clientId: number) {
  return useClientsMutation<void, Client>(() => api.post(`/clients/${clientId}/discord/sync`, {}))
}
