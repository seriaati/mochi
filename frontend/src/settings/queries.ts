import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '../api.ts'

export type Settings = {
  /** IANA name, e.g. Asia/Taipei. Due dates, "today" and 09:00 reminders follow it. */
  timezone: string
  /** What the dashboard calls the user. Null uses their Discord name. */
  user_name: string | null
  /** Shown in the top bar. Null shows "Studio". */
  studio_name: string | null
  /** A small image as a data: URL. Null shows a plain mark. */
  studio_logo: string | null
}

const keys = { all: ['settings'] as const }

export function useSettings() {
  return useQuery({ queryKey: keys.all, queryFn: () => api.get<Settings>('/settings') })
}

/**
 * Replaces all the settings. A new timezone can move "today", so maintenance and the clients'
 * flags refetch too.
 */
export function useSaveSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: Settings) => api.put<Settings>('/settings', input),
    onSuccess: () =>
      Promise.all([
        queryClient.invalidateQueries({ queryKey: keys.all }),
        queryClient.invalidateQueries({ queryKey: ['maintenance'] }),
        queryClient.invalidateQueries({ queryKey: ['clients'] }),
      ]),
  })
}
