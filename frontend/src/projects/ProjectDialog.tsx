import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { useClients } from '../clients/queries.ts'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { Select } from '../components/Select.tsx'
import { todayISO } from '../format.ts'
import { useDeleteProject, useSaveProject, type Project } from './queries.ts'

type Props = {
  /** The project to edit; omit to start a new one. */
  project?: Project
  /** Preselects the client for a new project. */
  clientId?: number
  onClose: () => void
  onSaved?: (project: Project) => void
  onDeleted?: () => void
}

export function ProjectDialog({ project, clientId, onClose, onSaved, onDeleted }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const clients = useClients()
  const save = useSaveProject(project?.id)
  const remove = useDeleteProject()
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [owner, setOwner] = useState(String(project?.client_id ?? clientId ?? ''))
  const error = save.error ?? remove.error

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const text = (name: string) => ((form.get(name) as string | null) ?? '').trim() || null
    save.mutate(
      {
        client_id: Number(form.get('client_id')),
        name: text('name') ?? '',
        description: text('description'),
        price: Number(form.get('price')),
        deposit_percent: Number(form.get('deposit_percent')),
        started_on: text('started_on') ?? '',
        due_on: text('due_on'),
        delivered_on: text('delivered_on'),
      },
      {
        onSuccess: (saved) => {
          close()
          onSaved?.(saved)
        },
      },
    )
  }

  if (clients.data?.length === 0) {
    return (
      <Dialog title="New project" ref={dialog} onClose={onClose}>
        <p className="empty-note">
          A project belongs to a client. <Link to="/clients">Add a client</Link> first.
        </p>
        <div className="form-actions">
          <button className="btn secondary" type="button" onClick={close}>
            Close
          </button>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog title={project ? 'Edit project' : 'New project'} ref={dialog} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <label className="field">
          Client
          <Select
            name="client_id"
            required
            value={owner}
            onChange={setOwner}
            placeholder={clients.isPending ? 'Loading clients…' : 'Choose a client'}
            options={(clients.data ?? []).map((c) => ({ value: String(c.id), label: c.name }))}
          />
        </label>
        <label className="field">
          Name
          <input name="name" required maxLength={200} defaultValue={project?.name} autoFocus />
        </label>
        <label className="field">
          Description
          <textarea name="description" defaultValue={project?.description ?? ''} />
        </label>
        <div className="form-row">
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
              defaultValue={project?.price}
            />
          </label>
          <label className="field">
            Deposit (%)
            <input
              name="deposit_percent"
              type="number"
              inputMode="numeric"
              required
              min={0}
              max={100}
              step={1}
              defaultValue={project?.deposit_percent ?? 50}
            />
          </label>
        </div>
        <div className="form-row">
          <label className="field">
            Started on
            <input
              name="started_on"
              type="date"
              required
              defaultValue={project?.started_on ?? todayISO()}
            />
          </label>
          <label className="field">
            Due on (optional)
            <input name="due_on" type="date" defaultValue={project?.due_on ?? ''} />
          </label>
        </div>
        {project && (
          <label className="field">
            Delivered on
            <input name="delivered_on" type="date" defaultValue={project.delivered_on ?? ''} />
            <small>Clear it if the project isn't delivered after all.</small>
          </label>
        )}
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            {project ? 'Save' : 'Create project'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {project && (
            <button
              className="btn danger"
              type="button"
              disabled={remove.isPending}
              onClick={() =>
                confirmDelete
                  ? remove.mutate(project.id, {
                      onSuccess: () => {
                        close()
                        onDeleted?.()
                      },
                    })
                  : setConfirmDelete(true)
              }
            >
              {confirmDelete ? 'Delete with its payments?' : 'Delete'}
            </button>
          )}
        </div>
      </form>
    </Dialog>
  )
}
