import { useQuery } from '@tanstack/react-query'
import { api } from '../api.ts'

/** Money received in a calendar year, up to today. All NTD. */
export type Earnings = {
  year: number
  /** Received in each month, January first. */
  months: number[]
  total: number
  /** The year before, from 1 January to the same date. */
  previous_total: number
  /** total vs previous_total; null when that is 0. */
  change_percent: number | null
}

/**
 * This year's earnings. Payments are recorded on other pages, whose mutations don't know about
 * this query, so it refetches whenever the Overview opens rather than staying fresh for 30 s.
 */
export function useEarnings() {
  return useQuery({
    queryKey: ['overview', 'earnings'],
    queryFn: () => api.get<Earnings>('/overview/earnings'),
    staleTime: 0,
  })
}
