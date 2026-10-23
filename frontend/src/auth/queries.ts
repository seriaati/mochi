import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import { api } from '../api.ts'

export type Session = { authenticated: boolean }

const sessionKey = ['auth', 'session'] as const

/** Whether this browser is logged in. Checked once per page load; any 401 later flips it. */
export function useSession() {
  return useQuery({
    queryKey: sessionKey,
    queryFn: () => api.get<Session>('/auth/session'),
    staleTime: Infinity,
    retry: false,
  })
}

/** Shows the login screen, which then clears the cache (see clearCache). */
export function loggedOut(queryClient: QueryClient) {
  if (queryClient.getQueryData<Session>(sessionKey)?.authenticated === false) return
  queryClient.setQueryData<Session>(sessionKey, { authenticated: false })
}

/**
 * Drops every cached query and mutation but the session check. Run once the app has unmounted:
 * clearing while its pages still render would only make them fetch everything again.
 */
export function clearCache(queryClient: QueryClient) {
  queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== sessionKey[0] })
  queryClient.getMutationCache().clear()
}

export function useLogin() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (password: string) => api.post<Session>('/auth/login', { password }),
    onSuccess: (session) => queryClient.setQueryData(sessionKey, session),
  })
}

export function useLogout() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<void>('/auth/logout', undefined),
    onSuccess: () => loggedOut(queryClient),
  })
}
