import { useRef, useState, type FormEvent } from 'react'
import { DatePicker } from '../components/DatePicker.tsx'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { Select } from '../components/Select.tsx'
import { formatNTD, todayISO } from '../format.ts'
import { nextAmount, targetOf, type Target } from './payments.ts'
import { useDeletePayment, useSavePayment, type Payment, type Project } from './queries.ts'

type Props = {
  project: Project
  /** The payment to edit; omit to record a new one. */
  payment?: Payment
  /** What a new payment is for. Defaults to the project itself. */
  target?: Target
  onClose: () => void
}

export function PaymentDialog({ project, payment, target: initial = null, onClose }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const save = useSavePayment(project.id, payment?.id)
  const remove = useDeletePayment(project.id)
  const [target, setTarget] = useState<Target>(payment ? payment.addition_id : initial)
  const [amount, setAmount] = useState(
    String(payment ? payment.amount : nextAmount(targetOf(project, initial))),
  )
  const error = save.error ?? remove.error

  // What this payment may cover: what's owed, plus its own amount if it already counts there.
  const ownAmount = (t: Target) => (payment && payment.addition_id === t ? payment.amount : 0)
  const available = targetOf(project, target).outstanding + ownAmount(target)
  const options = [
    { id: null, name: 'Project', outstanding: project.outstanding },
    ...project.additions,
  ].filter((t) => t.outstanding + ownAmount(t.id) > 0 || t.id === target)

  function pick(value: string) {
    const next = value === '' ? null : Number(value)
    setTarget(next)
    // A new payment follows the target's next expected amount; an edit keeps its amount.
    if (!payment) setAmount(String(nextAmount(targetOf(project, next))))
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    save.mutate(
      {
        addition_id: target,
        amount: Number(amount),
        paid_on: form.get('paid_on') as string,
        note: (form.get('note') as string).trim() || null,
      },
      { onSuccess: close },
    )
  }

  return (
    <Dialog title={payment ? 'Edit payment' : 'Record payment'} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          For
          <Select
            value={String(target ?? '')}
            onChange={pick}
            options={options.map((t) => ({
              value: String(t.id ?? ''),
              label: t.id === null ? `Project · ${project.name}` : t.name,
            }))}
          />
        </label>
        <div className="form-row">
          <label className="field">
            Amount (NT$)
            <input
              type="number"
              inputMode="numeric"
              required
              min={1}
              max={available}
              step={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              autoFocus
            />
            <small>Up to {formatNTD(available)}</small>
          </label>
          <label className="field">
            Paid on
            <DatePicker name="paid_on" required defaultValue={payment?.paid_on ?? todayISO()} />
          </label>
        </div>
        <label className="field">
          Note
          <input
            name="note"
            maxLength={200}
            placeholder="e.g. bank transfer"
            defaultValue={payment?.note ?? ''}
          />
        </label>
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {payment ? 'Save' : 'Record payment'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {payment && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate(payment.id, { onSuccess: close })}
            >
              Remove
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}
