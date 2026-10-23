import { useState, type FormEvent } from 'react'
import { Dialog } from '../components/Dialog.tsx'
import { contactKinds } from './contactKinds.ts'
import { useDeleteContact, useSaveContact, type Contact, type ContactKind } from './queries.ts'

type Props = {
  clientId: number
  /** The contact to edit; omit to add a new one. */
  contact?: Contact
  onClose: () => void
}

export function ContactDialog({ clientId, contact, onClose }: Props) {
  const [kind, setKind] = useState<ContactKind>(contact?.kind ?? 'discord')
  const save = useSaveContact(clientId, contact?.id)
  const remove = useDeleteContact(clientId)
  const error = save.error ?? remove.error

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const discordId = ((form.get('discord_user_id') as string | null) ?? '').trim()
    save.mutate(
      {
        kind,
        value: (form.get('value') as string).trim(),
        discord_user_id: kind === 'discord' && discordId ? discordId : null,
      },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog title={contact ? 'Edit contact' : 'Add contact'} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          Platform
          <select value={kind} onChange={(e) => setKind(e.target.value as ContactKind)}>
            {Object.entries(contactKinds).map(([value, { label }]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          {contactKinds[kind].field}
          <input
            name="value"
            type={kind === 'email' ? 'email' : 'text'}
            required
            maxLength={200}
            defaultValue={contact?.value}
            autoFocus
          />
        </label>
        {kind === 'discord' && (
          <label className="field">
            Discord user ID (optional)
            <input
              name="discord_user_id"
              inputMode="numeric"
              pattern="\d{17,19}"
              title="17 to 19 digits"
              defaultValue={contact?.discord_user_id ?? ''}
            />
            <small>In Discord, turn on Developer Mode, then right-click the user and Copy User ID.</small>
          </label>
        )}
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {contact ? 'Save' : 'Add contact'}
          </button>
          <button className="btn secondary push" type="button" onClick={onClose}>
            Cancel
          </button>
          {contact && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() => remove.mutate(contact.id, { onSuccess: onClose })}
            >
              Remove
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}
