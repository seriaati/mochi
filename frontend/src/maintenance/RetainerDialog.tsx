import { useRef, useState, type FormEvent } from 'react'
import { contactHandle, contactKinds } from '../clients/contactKinds.ts'
import { useClients, type Client } from '../clients/queries.ts'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { todayISO } from '../format.ts'
import { useDeleteRetainer, useSaveRetainer, type Collection, type Retainer } from './queries.ts'

type Props = {
  /** The retainer to edit; omit to add a new one. */
  retainer?: Retainer
  /** Preselects the client when adding from a client page. */
  clientId?: number
  onClose: () => void
}

/** The contact reminders suggest asking on: Discord first, then LINE, then anything. */
function defaultContact(client: Client | undefined): number | null {
  const contacts = client?.contacts ?? []
  const pick =
    contacts.find((c) => c.kind === 'discord') ??
    contacts.find((c) => c.kind === 'line') ??
    contacts[0]
  return pick?.id ?? null
}

export function RetainerDialog({ retainer, clientId, onClose }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const clients = useClients().data ?? []
  const save = useSaveRetainer(retainer?.id)
  const remove = useDeleteRetainer()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [owner, setOwner] = useState<number | undefined>(retainer?.client_id ?? clientId)
  const [collection, setCollection] = useState<Collection>(retainer?.collection ?? 'ask')
  // undefined until picked: falls back to the client's default contact.
  const [askVia, setAskVia] = useState<number | null | undefined>(retainer?.ask_via_id)
  const [startedOn, setStartedOn] = useState(retainer?.started_on ?? todayISO())
  // YYYY-MM; undefined until picked, then a past start date defaults to tracking this month.
  const [trackedFrom, setTrackedFrom] = useState(retainer?.tracked_from.slice(0, 7))
  const error = save.error ?? remove.error

  const client = clients.find((c) => c.id === owner)
  const contactId = askVia === undefined ? defaultContact(client) : askVia
  const startMonth = startedOn.slice(0, 7)
  const thisMonth = todayISO().slice(0, 7)
  const tracked = trackedFrom ?? (startMonth < thisMonth ? thisMonth : startMonth)

  function pickClient(value: string) {
    setOwner(Number(value))
    setAskVia(undefined)
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    save.mutate(
      {
        client_id: Number(form.get('client_id')),
        amount: Number(form.get('amount')),
        due_day: Number(form.get('due_day')),
        collection,
        ask_via_id: collection === 'ask' ? contactId : null,
        started_on: startedOn,
        ended_on: (form.get('ended_on') as string) || null,
        tracked_from: `${tracked}-01`,
      },
      { onSuccess: close },
    )
  }

  return (
    <Dialog title={retainer ? 'Edit retainer' : 'Add retainer'} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          Client
          <select name="client_id" required value={owner ?? ''} onChange={(e) => pickClient(e.target.value)}>
            <option value="" disabled>
              Choose a client
            </option>
            {clients.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </label>
        <div className="form-row">
          <label className="field">
            Per month (NT$)
            <input
              name="amount"
              type="number"
              inputMode="numeric"
              required
              min={1}
              step={1}
              defaultValue={retainer?.amount}
              autoFocus
            />
          </label>
          <label className="field">
            Due on day
            <input
              name="due_day"
              type="number"
              inputMode="numeric"
              required
              min={1}
              max={31}
              step={1}
              defaultValue={retainer?.due_day ?? 25}
            />
            <small>Shorter months fall due on their last day</small>
          </label>
        </div>
        <div className="field">
          <span id="collection-label">How it's paid</span>
          <div className="segmented" role="group" aria-labelledby="collection-label">
            <button type="button" aria-pressed={collection === 'ask'} onClick={() => setCollection('ask')}>
              I ask for it
            </button>
            <button
              type="button"
              aria-pressed={collection === 'auto_transfer'}
              onClick={() => setCollection('auto_transfer')}
            >
              Auto transfer
            </button>
          </div>
          <small>
            {collection === 'ask'
              ? 'You get a Discord reminder at 09:00 on the due date and record each payment.'
              : 'Counts as paid on the due date. No reminders.'}
          </small>
        </div>
        {collection === 'ask' && (
          <label className="field">
            Ask on
            <select
              value={contactId ?? ''}
              onChange={(e) => setAskVia(e.target.value ? Number(e.target.value) : null)}
            >
              {client?.contacts.map((c) => (
                <option key={c.id} value={c.id}>
                  {contactKinds[c.kind].label} · {contactHandle(c)}
                </option>
              ))}
              <option value="">No contact</option>
            </select>
          </label>
        )}
        <div className="form-row">
          <label className="field">
            Started on
            <input type="date" required value={startedOn} onChange={(e) => setStartedOn(e.target.value)} />
          </label>
          <label className="field">
            Ended on (optional)
            <input name="ended_on" type="date" defaultValue={retainer?.ended_on ?? ''} />
          </label>
        </div>
        <label className="field">
          Track from
          <input
            type="month"
            required
            min={startMonth}
            pattern="\d{4}-\d{2}"
            placeholder="YYYY-MM"
            value={tracked}
            onChange={(e) => setTrackedFrom(e.target.value)}
          />
          <small>
            Earlier months count as settled: never overdue or reminded, and left out of totals. The start
            date stays as a record of when the work began.
          </small>
        </label>
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {retainer ? 'Save' : 'Add retainer'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {retainer && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() =>
                confirmingDelete
                  ? remove.mutate(retainer.id, { onSuccess: close })
                  : setConfirmingDelete(true)
              }
            >
              {confirmingDelete ? 'Confirm delete' : 'Delete'}
            </button>
          )}
        </div>
        {confirmingDelete && !remove.error && (
          <p className="field">This also removes its recorded payments and reminder history.</p>
        )}
      </form>
    </Dialog>
  )
}
