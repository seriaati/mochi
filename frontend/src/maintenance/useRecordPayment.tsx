import { useState } from 'react'
import type { Retainer } from './queries.ts'
import { RecordRetainerPaymentDialog } from './RetainerPaymentDialog.tsx'

/**
 * Record payment for a tile: the dialog to render, and a function that opens it. The tile keeps
 * the dialog in every state it can show, so it stays open while the payment it records moves the
 * tile on, e.g. from "Next to collect" to the next month.
 */
export function useRecordPayment() {
  const [open, setOpen] = useState<{ retainer: Retainer; period: string }>()
  const dialog = open && (
    <RecordRetainerPaymentDialog retainer={open.retainer} period={open.period} onClose={() => setOpen(undefined)} />
  )
  return [dialog, (retainer: Retainer, period: string) => setOpen({ retainer, period })] as const
}
