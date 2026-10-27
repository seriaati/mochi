import { useRef, useState, type FormEvent } from 'react'
import { DatePicker } from '../components/DatePicker.tsx'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { Select } from '../components/Select.tsx'
import { formatDay, formatNTD, todayISO } from '../format.ts'
import { monthName, monthRange, openMonths } from './labels.ts'
import {
  useDeleteRetainerPayment,
  useGiveUpMonth,
  useRecordRetainerPayment,
  type Month,
  type Retainer,
} from './queries.ts'
import './RetainerPaymentDialog.css'

type RecordProps = { retainer: Retainer; period?: string; onClose: () => void }

const monthLabel = (month: Month) =>
  `${monthName(month.period, true)} ${month.period.slice(0, 4)} · due ${formatDay(month.due_on)}`

/**
 * Marks one month of an "ask" retainer as paid, or several in a row when the client pays ahead.
 * An overdue month can be given up instead, e.g. one too old to ask for.
 */
export function RecordRetainerPaymentDialog({ retainer, period, onClose }: RecordProps) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const record = useRecordRetainerPayment(retainer.id)
  const giveUp = useGiveUpMonth(retainer.id)
  const months = openMonths(retainer)
  const [picked, setPicked] = useState(period ?? months[0]?.period ?? '')
  const [givingUp, setGivingUp] = useState(false)
  const overdue = months.find((m) => m.period === picked)?.status === 'overdue'
  const [count, setCount] = useState(1)
  // Undefined until typed: follows the fee times the months covered.
  const [amount, setAmount] = useState<string>()

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    record.mutate(
      {
        period: picked,
        months: count,
        amount: Number(form.get('amount')),
        paid_on: form.get('paid_on') as string,
      },
      { onSuccess: close },
    )
  }

  return (
    <Dialog title={`Record payment · ${retainer.client.name}`} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          For
          <Select
            value={picked}
            onChange={(next) => {
              setPicked(next)
              setGivingUp(false)
            }}
            options={months.map((m) => {
              const flag = m.status === 'overdue' ? ' · overdue' : m.status === 'due' ? ' · due' : ''
              return { value: m.period, label: monthLabel(m) + flag }
            })}
          />
        </label>
        <div className="form-row">
          <label className="field">
            Months covered
            <input
              type="number"
              inputMode="numeric"
              required
              min={1}
              max={12}
              step={1}
              value={count || ''}
              onChange={(e) => setCount(Number(e.target.value))}
            />
            <small>{count > 1 && picked ? monthRange(picked, count) : 'More than 1 when paid ahead'}</small>
          </label>
          <label className="field">
            Amount (NT$)
            <input
              name="amount"
              type="number"
              inputMode="numeric"
              required
              min={1}
              step={1}
              value={amount ?? retainer.amount * Math.max(count, 1)}
              onChange={(e) => setAmount(e.target.value)}
            />
            {count > 1 && <small>For all {count} months together</small>}
          </label>
        </div>
        <label className="field">
          Paid on
          <DatePicker name="paid_on" required defaultValue={todayISO()} autoFocus />
        </label>
        {record.error && <p className="form-error">{record.error.message}</p>}
        {giveUp.error && <p className="form-error">{giveUp.error.message}</p>}
        {givingUp && !giveUp.error && (
          <p className="field">
            {monthName(picked, true)} won&rsquo;t be overdue or reminded any more, and isn&rsquo;t counted as
            received.
          </p>
        )}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={record.isPending || !picked}>
            Record payment
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {overdue && (
            <button
              className="btn danger"
              type="button"
              disabled={giveUp.isPending}
              onClick={() => (givingUp ? giveUp.mutate(picked, { onSuccess: close }) : setGivingUp(true))}
            >
              {givingUp ? 'Confirm give up' : 'Give up'}
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}

type ViewProps = { retainer: Retainer; month: Month; onClose: () => void }

/** A recorded payment, for one month or several. To change one, remove it and record it again. */
export function RetainerPaymentDialog({ retainer, month, onClose }: ViewProps) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const remove = useDeleteRetainerPayment(retainer.id)
  const payment = month.payment

  return (
    <Dialog
      title={`${retainer.client.name} · ${monthName(month.period, true)} ${month.period.slice(0, 4)}`}
      ref={dialog}
      onClose={onClose}
    >
      <dl className="retainer-facts">
        <div>
          <dt>Amount</dt>
          <dd>{formatNTD(payment?.amount ?? month.amount)}</dd>
        </div>
        {payment && payment.months > 1 && (
          <div>
            <dt>Covers</dt>
            <dd>
              {monthRange(payment.period, payment.months)} · {formatNTD(month.amount)} this month
            </dd>
          </div>
        )}
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
        <button className="btn secondary push" type="button" onClick={close}>
          Close
        </button>
        {payment && (
          <button
            className="btn danger"
            type="button"
            disabled={remove.isPending}
            onClick={() => remove.mutate(payment.id, { onSuccess: close })}
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
