import { useRef, useState, type FormEvent } from 'react'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { useSaveClient, type Client } from './queries.ts'

type Props = {
  /** The client to edit; omit to add a new one. */
  client?: Client
  onClose: () => void
  onSaved?: (client: Client) => void
}

export function ClientDialog({ client, onClose, onSaved }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const save = useSaveClient(client?.id)
  const [discordId, setDiscordId] = useState('')

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (name: string) => (form.get(name) as string).trim() || null
    const fields = {
      name: text('name') ?? '',
      contact_person: text('contact_person'),
      notes: text('notes'),
    }
    save.mutate(
      client ? fields : { ...fields, discord_user_id: text('discord_user_id') },
      {
        onSuccess: (saved) => {
          close()
          onSaved?.(saved)
        },
      },
    )
  }

  return (
    <Dialog title={client ? 'Edit client' : 'Add client'} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        {!client && (
          <label className="field">
            Discord user ID (optional)
            <input
              name="discord_user_id"
              inputMode="numeric"
              pattern="\d{17,19}"
              title="17 to 19 digits"
              value={discordId}
              onChange={(e) => setDiscordId(e.target.value.trim())}
              autoFocus
            />
            <small>Adds them as a Discord contact. In Discord, turn on Developer Mode, then right-click the user and Copy User ID.</small>
          </label>
        )}
        <label className="field">
          Name
          <input
            name="name"
            required={!discordId}
            maxLength={200}
            defaultValue={client?.name}
            placeholder={discordId ? 'Their Discord name' : undefined}
            autoFocus={!!client}
          />
        </label>
        <label className="field">
          Contact person
          <input name="contact_person" maxLength={200} defaultValue={client?.contact_person ?? ''} />
        </label>
        <label className="field">
          Notes
          <textarea name="notes" defaultValue={client?.notes ?? ''} />
        </label>
        {save.error && <p className="form-error">{save.error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {client ? 'Save' : 'Add client'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
        </div>
      </form>
    </Dialog>
  )
}
