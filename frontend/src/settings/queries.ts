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
  /** Maintenance reminders post here. Null turns them off. */
  discord_webhook_url: string | null
  /** The user's own Discord ID, @mentioned in each reminder. */
  discord_mention_user_id: string | null
  /** The bot token itself never leaves the API. */
  readonly discord_bot_token_set: boolean
  /** Without ENCRYPTION_KEY on the API, no bot token can be saved. */
  readonly encryption_key_set: boolean
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

/**
 * Saves the bot token (the API encrypts it), or removes it with null. Sync status shows on
 * clients, projects and maintenance, so everything refetches.
 */
export function useSaveBotToken() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (token: string | null) => {
      if (token === null) await api.delete('/settings/discord-bot-token')
      else await api.put('/settings/discord-bot-token', { token })
    },
    onSuccess: () => queryClient.invalidateQueries(),
  })
}
