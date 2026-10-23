import { useState, type FormEvent } from 'react'
import { Dialog } from '../components/Dialog.tsx'
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
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog title={payment ? 'Edit payment' : 'Record payment'} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          For
          <select value={target ?? ''} onChange={(e) => pick(e.target.value)}>
            {options.map((t) => (
              <option key={t.id ?? 'project'} value={t.id ?? ''}>
                {t.id === null ? `Project · ${project.name}` : t.name}
              </option>
            ))}
          </select>
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
            <input
              name="paid_on"
              type="date"
              required
              defaultValue={payment?.paid_on ?? todayISO()}
            />
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
          <button className="btn secondary push" type="button" onClick={onClose}>
            Cancel
          </button>
          {payment && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate(payment.id, { onSuccess: onClose })}
            >
              Remove
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}
