import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '../api.ts'

/** An MCP client (e.g. Claude) asking for access, waiting for the user's answer. */
export type AccessRequest = {
  /** As the client registered itself: anyone can claim any name. */
  client_name: string | null
  /** Where the code goes on approval. Its host shows who really receives access. */
  redirect_uri: string
}

export function useAccessRequest(id: string) {
  return useQuery({
    queryKey: ['oauth', 'requests', id],
    queryFn: () => api.get<AccessRequest>(`/oauth/requests/${encodeURIComponent(id)}`),
    retry: false,
  })
}

/** Answers the request, then leaves for the client: with a code, or with access_denied. */
export function useAnswer(id: string) {
  return useMutation({
    mutationFn: (approve: boolean) =>
      api.post<{ redirect_uri: string }>(`/oauth/requests/${encodeURIComponent(id)}`, { approve }),
    onSuccess: ({ redirect_uri }) => window.location.assign(redirect_uri),
  })
}
