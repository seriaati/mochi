import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router'
import { Dialog } from '../components/Dialog.tsx'
import { useDeleteClient, useSaveClient, type Client } from './queries.ts'

type Props = {
  /** The client to edit; omit to add a new one. */
  client?: Client
  onClose: () => void
  onSaved?: (client: Client) => void
}

export function ClientDialog({ client, onClose, onSaved }: Props) {
  const save = useSaveClient(client?.id)
  const remove = useDeleteClient(client?.id ?? 0)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const navigate = useNavigate()
  const error = save.error ?? remove.error

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (name: string) => (form.get(name) as string).trim() || null
    save.mutate(
      { name: text('name') ?? '', contact_person: text('contact_person'), notes: text('notes') },
      {
        onSuccess: (saved) => {
          onClose()
          onSaved?.(saved)
        },
      },
    )
  }

  return (
    <Dialog title={client ? 'Edit client' : 'Add client'} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          Name
          <input name="name" required maxLength={200} defaultValue={client?.name} autoFocus />
        </label>
        <label className="field">
          Contact person
          <input name="contact_person" maxLength={200} defaultValue={client?.contact_person ?? ''} />
        </label>
        <label className="field">
          Notes
          <textarea name="notes" defaultValue={client?.notes ?? ''} />
        </label>
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {client ? 'Save' : 'Add client'}
          </button>
          <button className="btn secondary push" type="button" onClick={onClose}>
            Cancel
          </button>
          {client && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() =>
                confirmingDelete
                  ? remove.mutate(undefined, { onSuccess: () => navigate('/clients') })
                  : setConfirmingDelete(true)
              }
            >
              {confirmingDelete ? 'Confirm delete' : 'Delete'}
            </button>
          )}
        </div>
        {confirmingDelete && !remove.error && (
          <p className="field">This also removes the client&rsquo;s contact methods.</p>
        )}
      </form>
    </Dialog>
  )
}
