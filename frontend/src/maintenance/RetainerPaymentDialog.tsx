import { useState, type FormEvent } from 'react'
import { Dialog } from '../components/Dialog.tsx'
import { formatDay, formatNTD, todayISO } from '../format.ts'
import { monthName, openMonths } from './labels.ts'
import {
  useDeleteRetainerPayment,
  useRecordRetainerPayment,
  type Month,
  type Retainer,
} from './queries.ts'
import './RetainerPaymentDialog.css'

type RecordProps = { retainer: Retainer; period?: string; onClose: () => void }

const monthLabel = (month: Month) =>
  `${monthName(month.period, true)} ${month.period.slice(0, 4)} · due ${formatDay(month.due_on)}`

/** Marks one month of an "ask" retainer as paid. */
export function RecordRetainerPaymentDialog({ retainer, period, onClose }: RecordProps) {
  const record = useRecordRetainerPayment(retainer.id)
  const months = openMonths(retainer)
  const [picked, setPicked] = useState(period ?? months[0]?.period ?? '')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    record.mutate(
      { period: picked, amount: Number(form.get('amount')), paid_on: form.get('paid_on') as string },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog title={`Record payment · ${retainer.client.name}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          For
          <select value={picked} required onChange={(e) => setPicked(e.target.value)}>
            {months.map((m) => (
              <option key={m.period} value={m.period}>
                {monthLabel(m)}
                {m.status === 'overdue' ? ' · overdue' : m.status === 'due' ? ' · due' : ''}
              </option>
            ))}
          </select>
        </label>
        <div className="form-row">
          <label className="field">
            Amount (NT$)
            <input
              name="amount"
              type="number"
              inputMode="numeric"
              required
              min={1}
              step={1}
              defaultValue={retainer.amount}
            />
          </label>
          <label className="field">
            Paid on
            <input name="paid_on" type="date" required defaultValue={todayISO()} autoFocus />
          </label>
        </div>
        {record.error && <p className="form-error">{record.error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={record.isPending || !picked}>
            Record payment
          </button>
          <button className="btn secondary" type="button" onClick={onClose}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  )
}

type ViewProps = { retainer: Retainer; month: Month; onClose: () => void }

/** A recorded monthly payment. To change one, remove it and record it again. */
export function RetainerPaymentDialog({ retainer, month, onClose }: ViewProps) {
  const remove = useDeleteRetainerPayment(retainer.id)

  return (
    <Dialog
      title={`${retainer.client.name} · ${monthName(month.period, true)} ${month.period.slice(0, 4)}`}
      onClose={onClose}
    >
      <dl className="retainer-facts">
        <div>
          <dt>Amount</dt>
          <dd>{formatNTD(month.amount)}</dd>
        </div>
        <div>
          <dt>Paid on</dt>
          <dd>{month.paid_on && formatDay(month.paid_on, { weekday: true, year: true })}</dd>
        </div>
        <div>
          <dt>Due on</dt>
          <dd>
            {formatDay(month.due_on, { weekday: true, year: true })}
            {month.late && ` · paid ${month.days_late} days late`}
          </dd>
        </div>
      </dl>
      {remove.error && <p className="form-error">{remove.error.message}</p>}
      <div className="form-actions">
        <button className="btn secondary push" type="button" onClick={onClose}>
          Close
        </button>
        {month.payment_id !== null && (
          <button
            className="btn danger"
            type="button"
            disabled={remove.isPending}
            onClick={() => remove.mutate(month.payment_id!, { onSuccess: onClose })}
          >
            Remove payment
          </button>
        )}
      </div>
    </Dialog>
  )
}

/** For a month chip: view the recorded payment of a paid month, or record one for an unpaid month. */
export function MonthDialog({ retainer, month, onClose }: ViewProps) {
  return month.status === 'paid' ? (
    <RetainerPaymentDialog retainer={retainer} month={month} onClose={onClose} />
  ) : (
    <RecordRetainerPaymentDialog retainer={retainer} period={month.period} onClose={onClose} />
  )
}
