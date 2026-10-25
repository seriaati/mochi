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

export type Keni = {
  /** Keni's base URL. Null while not connected, as are the fields below but pending. */
  url: string | null
  /** Where new income is recorded, changeable while connected. */
  wallet_id: string | null
  wallet_name: string | null
  wallet_currency: string | null
  category_id: string | null
  category_name: string | null
  /** Money already received by this day stays out of Keni. */
  connected_on: string | null
  /** Changes still to send. The API syncs every minute. */
  pending: number
  /** Why the last sync stopped. */
  error: string | null
}

export type KeniOptions = {
  wallets: { id: string; name: string; currency: string }[]
  categories: { id: string; name: string }[]
}

export type KeniDestination = { wallet_id: string; category_id: string }

type KeniLogin = { url: string; token: string }

const keniKey = ['settings', 'keni'] as const

/** Refetches every 15 seconds while changes wait or a sync failed, to show the loop catching up. */
export function useKeni() {
  return useQuery({
    queryKey: keniKey,
    queryFn: () => api.get<Keni>('/settings/keni'),
    refetchInterval: (query) => (query.state.data?.pending || query.state.data?.error ? 15_000 : false),
  })
}

/** The wallets and categories a Keni API key can record in, to pick from before connecting. */
export function useFindKeniOptions() {
  return useMutation({
    mutationFn: (login: KeniLogin) => api.post<KeniOptions>('/settings/keni/options', login),
  })
}

/** The connected account's wallets and categories, fetched with the saved key. */
export function useKeniOptions() {
  return useQuery({
    queryKey: [...keniKey, 'options'],
    queryFn: () => api.get<KeniOptions>('/settings/keni/options'),
  })
}

/** Connects to Keni, or disconnects with null. */
export function useConnectKeni() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async (input: (KeniLogin & KeniDestination) | null) =>
      input === null ? api.delete('/settings/keni') : api.put<Keni>('/settings/keni', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keniKey }),
  })
}

/** Records income sent from now on in another wallet or category. */
export function useChooseKeniDestination() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: KeniDestination) => api.put<Keni>('/settings/keni/destination', input),
    onSuccess: (keni) => queryClient.setQueryData(keniKey, keni),
  })
}
