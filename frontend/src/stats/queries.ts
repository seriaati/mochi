import { useQuery } from '@tanstack/react-query'
import { api } from '../api.ts'
import type { Collection } from '../maintenance/queries.ts'

export type Source = 'project' | 'addition' | 'retainer'

type Ref = { id: number; name: string }

/** Money received, counted as the Overview's earnings count it. NTD. */
export type IncomeEntry = {
  /** Auto transfers: the month's due date. */
  paid_on: string
  amount: number
  source: Source
  /** Who paid. */
  client: Ref
  /** What for: the project, the addition's, or the retainer's if any. */
  project: Ref | null
  addition: Ref | null
  /** Retainers only. */
  collection: Collection | null
  /** Retainers only: days paid after the due date, 0 when on time or ahead. */
  days_late: number | null
  /** Retainers only: paid more than the 2 grace days after the due date. */
  late: boolean | null
}

export type Income = {
  /** In the saved timezone. */
  today: string
  /** Oldest first. */
  entries: IncomeEntry[]
}

/** Everything received up to today. Refetched on each visit, like the Overview's earnings. */
export function useIncome() {
  return useQuery({
    queryKey: ['stats', 'income'],
    queryFn: () => api.get<Income>('/stats/income'),
    staleTime: 0,
  })
}
