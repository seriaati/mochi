import { useRef, useState, type FormEvent } from 'react'
import { contactHandle, contactKinds } from '../clients/contactKinds.ts'
import { useClients, type Client } from '../clients/queries.ts'
import { DatePicker } from '../components/DatePicker.tsx'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { Segmented } from '../components/Segmented.tsx'
import { Select } from '../components/Select.tsx'
import { formatDay, todayISO } from '../format.ts'
import { useProjects } from '../projects/queries.ts'
import { monthName } from './labels.ts'
import {
  useDeleteRetainer,
  usePauseRetainer,
  useResumeRetainer,
  useSaveRetainer,
  useSwitchToAuto,
  type Collection,
  type Retainer,
} from './queries.ts'
import './RetainerDialog.css'

type Props = {
  /** The retainer to edit; omit to add a new one. */
  retainer?: Retainer
  /** Preselects the client when adding from a client page. */
  clientId?: number
  /** Preselects the project when adding from a project page. */
  projectId?: number
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

/** "Aug 2026" from YYYY-MM. */
function shortMonth(month: string): string {
  return `${monthName(`${month}-01`)} ${month.slice(0, 4)}`
}

export function RetainerDialog({ retainer, clientId, projectId, onClose }: Props) {
  const dialog = useRef<DialogHandle>(null)
  const close = () => dialog.current?.close()
  const clients = useClients().data ?? []
  const projects = useProjects().data ?? []
  const save = useSaveRetainer(retainer?.id)
  const remove = useDeleteRetainer()
  const pause = usePauseRetainer(retainer?.id ?? 0)
  const resume = useResumeRetainer(retainer?.id ?? 0)
  const switchToAuto = useSwitchToAuto(retainer?.id ?? 0)
  // Pause and Delete each confirm on a second press, with what they do spelled out below.
  const [confirming, setConfirming] = useState<'pause' | 'delete'>()
  const [owner, setOwner] = useState<number | undefined>(retainer?.client_id ?? clientId)
  const [project, setProject] = useState(retainer ? retainer.project_id : (projectId ?? null))
  const [dueDay, setDueDay] = useState(String(retainer?.due_day ?? 25))
  const [collection, setCollection] = useState<Collection>(retainer?.collection ?? 'ask')
  // undefined until picked: falls back to the client's default contact.
  const [askVia, setAskVia] = useState<number | null | undefined>(retainer?.ask_via_id)
  const [startedOn, setStartedOn] = useState(retainer?.started_on ?? todayISO())
  const [endedOn, setEndedOn] = useState(retainer?.ended_on ?? '')
  // YYYY-MM; undefined until picked, then a past start date defaults to tracking this month.
  const [trackedFrom, setTrackedFrom] = useState(retainer?.tracked_from.slice(0, 7))
  const error = save.error ?? switchToAuto.error ?? remove.error ?? pause.error ?? resume.error
  const ended = !!retainer?.ended_on && retainer.ended_on < todayISO()
  // An "ask" retainer moving to auto transfer keeps the months before switchFrom as they were.
  const switching = retainer?.collection === 'ask' && !ended && collection === 'auto_transfer'
  // YYYY-MM; defaults to the next month due, so months already owed stay owed.
  const [switchFrom, setSwitchFrom] = useState((retainer?.next_due_on ?? todayISO()).slice(0, 7))

  const client = clients.find((c) => c.id === owner)
  const contactId = askVia === undefined ? defaultContact(client) : askVia
  const startMonth = startedOn.slice(0, 7)
  const thisMonth = todayISO().slice(0, 7)
  const tracked = trackedFrom ?? (startMonth < thisMonth ? thisMonth : startMonth)
  const dates = [
    `Since ${formatDay(startedOn, { year: true })}`,
    endedOn ? `until ${formatDay(endedOn, { year: true })}` : 'no end date',
    ...(tracked > startMonth ? [`tracked from ${shortMonth(tracked)}`] : []),
  ].join(' · ')

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
        project_id: project,
        amount: Number(form.get('amount')),
        due_day: Number(dueDay),
        collection: switching ? 'ask' : collection,
        ask_via_id: collection === 'ask' || switching ? contactId : null,
        started_on: startedOn,
        ended_on: endedOn || null,
        tracked_from: `${tracked}-01`,
      },
      {
        onSuccess: () => (switching ? switchToAuto.mutate(`${switchFrom}-01`, { onSuccess: close }) : close()),
      },
    )
  }

  return (
    <Dialog title={retainer ? 'Edit retainer' : 'Add retainer'} ref={dialog} onClose={onClose}>
      <form className="form rd-form" onSubmit={submit}>
        <div className="rd-group">
          <label className="field">
            Client
            <Select
              name="client_id"
              required
              value={String(owner ?? '')}
              onChange={pickClient}
              placeholder="Choose a client"
              options={clients.map((c) => ({ value: String(c.id), label: c.name }))}
            />
          </label>
          <label className="field">
            Project
            <Select
              value={String(project ?? '')}
              onChange={(value) => setProject(value ? Number(value) : null)}
              options={[
                { value: '', label: 'No project' },
                ...projects.map((p) => ({ value: String(p.id), label: p.name })),
              ]}
            />
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
                type="number"
                inputMode="numeric"
                required
                min={1}
                max={31}
                step={1}
                value={dueDay}
                onChange={(event) => setDueDay(event.target.value)}
              />
              {Number(dueDay) > 28 && <small>Shorter months fall due on their last day</small>}
            </label>
          </div>
        </div>

        <div className="rd-group">
          <div className="field">
            <span id="collection-label">How it's paid</span>
            <Segmented className="rd-collection" role="group" aria-labelledby="collection-label">
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
            </Segmented>
          </div>
          {collection === 'ask' ? (
            <label className="field">
              Ask on
              <Select
                value={String(contactId ?? '')}
                onChange={(value) => setAskVia(value ? Number(value) : null)}
                options={[
                  ...(client?.contacts ?? []).map((c) => ({
                    value: String(c.id),
                    label: `${contactKinds[c.kind].label} · ${contactHandle(c)}`,
                  })),
                  { value: '', label: 'No contact' },
                ]}
              />
              <small>You're reminded at 09:00 on the due date until you record the payment.</small>
            </label>
          ) : switching ? (
            <label className="field">
              Auto transfer from
              <DatePicker month required min={tracked} value={switchFrom} onChange={setSwitchFrom} />
              <small>
                {switchFrom > tracked
                  ? 'Earlier months stay asked for, with their payments. From this month it carries on as a new retainer.'
                  : 'Every tracked month counts as paid on its due date.'}
              </small>
            </label>
          ) : (
            <p className="rd-note">Counts as paid on the due date, with no reminders.</p>
          )}
        </div>

        {/* Set once and rarely changed, so folded away when editing. */}
        <details className="rd-dates" open={!retainer}>
          <summary>
            <span className="rd-dates-label">Dates</span>
            <span className="rd-dates-value">{dates}</span>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m6 9 6 6 6-6" />
            </svg>
          </summary>
          <div className="rd-dates-body">
            <div className="form-row">
              <label className="field">
                Started on
                <DatePicker required value={startedOn} onChange={setStartedOn} />
              </label>
              <label className="field">
                Ends on
                <DatePicker value={endedOn} onChange={setEndedOn} placeholder="No end date" />
              </label>
            </div>
            <label className="field">
              Track from
              <DatePicker month required min={startMonth} value={tracked} onChange={setTrackedFrom} />
              <small>Earlier months count as settled: never overdue or reminded, and left out of totals.</small>
            </label>
          </div>
        </details>

        {retainer?.paused_on && (
          <p className="rd-note">
            Paused since {formatDay(retainer.paused_on)}: no months are billed and no reminders go out.
          </p>
        )}
        {error && <p className="form-error">{error.message}</p>}
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending || switchToAuto.isPending}>
            {retainer ? 'Save' : 'Add retainer'}
          </button>
          <button className="btn secondary push" type="button" onClick={close}>
            Cancel
          </button>
          {/* Wraps onto its own line as one, rather than splitting Pause from Delete. */}
          <div className="rd-lifecycle">
            {retainer?.paused_on ? (
              <button
                className="btn secondary"
                type="button"
                disabled={resume.isPending}
                onClick={() => resume.mutate(undefined, { onSuccess: close })}
              >
                Resume
              </button>
            ) : (
              retainer &&
              !ended && (
                <button
                  className="btn secondary"
                  type="button"
                  disabled={pause.isPending}
                  onClick={() =>
                    confirming === 'pause' ? pause.mutate(undefined, { onSuccess: close }) : setConfirming('pause')
                  }
                >
                  {confirming === 'pause' ? 'Confirm pause' : 'Pause'}
                </button>
              )
            )}
            {retainer && (
              <button
                className="btn danger"
                type="button"
                disabled={remove.isPending}
                onClick={() =>
                  confirming === 'delete' ? remove.mutate(retainer.id, { onSuccess: close }) : setConfirming('delete')
                }
              >
                {confirming === 'delete' ? 'Confirm delete' : 'Delete'}
              </button>
            )}
          </div>
        </div>
        {confirming === 'pause' && !pause.error && (
          <p className="rd-note">
            For a client who stopped paying: billing and reminders stop from today, and what they owe stays on
            record.
          </p>
        )}
        {confirming === 'delete' && !remove.error && (
          <p className="rd-note">This also removes its recorded payments and reminder history.</p>
        )}
      </form>
    </Dialog>
  )
}
