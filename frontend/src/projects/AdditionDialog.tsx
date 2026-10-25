import { useRef, useState, type FormEvent } from 'react'
import { DatePicker } from '../components/DatePicker.tsx'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { Select } from '../components/Select.tsx'
import { todayISO } from '../format.ts'
import { useDeleteAddition, useSaveAddition, type Addition } from './queries.ts'

type Props = {
  projectId: number
  /** The addition to edit; omit to add a new one. */
  addition?: Addition
  onClose: () => void
}

export function AdditionDialog({ projectId, addition, onClose }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const save = useSaveAddition(projectId, addition?.id)
  const remove = useDeleteAddition(projectId)
  const [split, setSplit] = useState((addition?.deposit_percent ?? 0) > 0)
  const [confirmRemove, setConfirmRemove] = useState(false)
  const error = save.error ?? remove.error

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (name: string) => ((form.get(name) as string | null) ?? '').trim() || null
    save.mutate(
      {
        name: text('name') ?? '',
        description: text('description'),
        price: Number(form.get('price')),
        deposit_percent: split ? Number(form.get('deposit_percent')) : 0,
        agreed_on: text('agreed_on') ?? '',
        delivered_on: text('delivered_on'),
      },
      { onSuccess: close },
    )
  }

  return (
    <Dialog title={addition ? 'Edit addition' : 'Add addition'} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          Name
          <input
            name="name"
            required
            maxLength={200}
            placeholder="e.g. Giveaway feature"
            defaultValue={addition?.name}
            autoFocus
          />
        </label>
        <label className="field">
          Description
          <textarea name="description" defaultValue={addition?.description ?? ''} />
        </label>
        <label className="field">
          Price (NT$)
          <input
            name="price"
            type="number"
            inputMode="numeric"
            required
            min={0}
            max={2_000_000_000}
            step={1}
            defaultValue={addition?.price}
          />
        </label>
        <div className="form-row">
          <label className="field">
            Payment terms
            <Select
              value={split ? 'split' : 'single'}
              onChange={(value) => setSplit(value === 'split')}
              options={[
                { value: 'single', label: 'Single payment' },
                { value: 'split', label: 'Deposit, rest on delivery' },
              ]}
            />
          </label>
          {split && (
            <label className="field">
              Deposit (%)
              <input
                name="deposit_percent"
                type="number"
                inputMode="numeric"
                required
                min={1}
                max={100}
                step={1}
                defaultValue={addition?.deposit_percent || 50}
              />
            </label>
          )}
        </div>
        <div className="form-row">
          <label className="field">
            Agreed on
            <DatePicker name="agreed_on" required defaultValue={addition?.agreed_on ?? todayISO()} />
          </label>
          <label className="field">
            Delivered on
            <DatePicker name="delivered_on" defaultValue={addition?.delivered_on ?? ''} />
          </label>
        </div>
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {addition ? 'Save' : 'Add addition'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {addition && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() =>
                confirmRemove || addition.paid === 0
                  ? remove.mutate(addition.id, { onSuccess: close })
                  : setConfirmRemove(true)
              }
            >
              {confirmRemove ? 'Remove with its payments?' : 'Remove'}
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}
