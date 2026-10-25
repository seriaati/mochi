import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { contactHandle } from '../clients/contactKinds.ts'
import { KindLabel } from '../clients/KindLabel.tsx'
import { useClient } from '../clients/queries.ts'
import { Avatar } from '../components/Avatar.tsx'
import { formatDay, formatNTD, formatNumber, initials, plural, todayISO } from '../format.ts'
import { monthChip, scheduleText } from '../maintenance/labels.ts'
import { useProjectRetainers, type Month, type Retainer } from '../maintenance/queries.ts'
import { RetainerDialog } from '../maintenance/RetainerDialog.tsx'
import { MonthDialog } from '../maintenance/RetainerPaymentDialog.tsx'
import { tintClass } from '../tint.ts'
import { AdditionDialog } from './AdditionDialog.tsx'
import { paymentLabel, type Target } from './payments.ts'
import { PaymentDialog } from './PaymentDialog.tsx'
import { ProjectDialog } from './ProjectDialog.tsx'
import {
  additionInput,
  projectInput,
  useDeleteProject,
  useProject,
  useSaveAddition,
  useSaveProject,
  type Addition,
  type Billing,
  type Payment,
  type Project,
} from './queries.ts'
import { daysIn, daysLeft, dueText, elapsedPercent, statusLabels, type Tone } from './schedule.ts'
import { Track } from './Track.tsx'
import './ProjectDetailPage.css'

export function ProjectDetailPage() {
  const id = Number(useParams().id)
  const project = useProject(id)

  return (
    <>
      <Link className="back" to="/projects">
        ← Projects
      </Link>
      {project.isPending && <p className="status">Loading project…</p>}
      {project.error && <p className="status">Couldn't load this project: {project.error.message}</p>}
      {project.data && <ProjectTiles project={project.data} />}
    </>
  )
}

const statusTones: Record<Project['status'], Tone> = {
  in_progress: 'good',
  final_payment_due: 'warn',
  done: 'good',
}

function ProjectTiles({ project }: { project: Project }) {
  const [editing, setEditing] = useState(false)
  // undefined = closed, null = adding, an addition = editing it.
  const [addition, setAddition] = useState<Addition | null>()
  // undefined = closed, otherwise the target to pay.
  const [paying, setPaying] = useState<{ target: Target }>()
  const [payment, setPayment] = useState<Payment>()
  const remove = useDeleteProject()
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const navigate = useNavigate()
  const { client } = project

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title project-title">{project.name}</h1>
          {project.description && <p className="project-description">{project.description}</p>}
          <div className="project-tags">
            <Link className="chip" to={`/clients/${client.id}`}>
              <Avatar
                className={`project-mini ${tintClass(client.id)}`}
                src={client.avatar_url}
                fallback={initials(client.name)}
              />
              {client.name}
            </Link>
            <span className={`chip ${statusTones[project.status]}`}>{statusLabels[project.status]}</span>
            {project.additions.length > 0 && (
              <span className="chip">{plural(project.additions.length, 'addition')}</span>
            )}
          </div>
        </div>
        <div className="page-actions">
          <button className="btn secondary" type="button" onClick={() => setEditing(true)}>
            Edit
          </button>
          <button
            className="btn danger"
            type="button"
            disabled={remove.isPending}
            onClick={() =>
              confirmingDelete
                ? remove.mutate(project.id, { onSuccess: () => navigate('/projects', { replace: true }) })
                : setConfirmingDelete(true)
            }
          >
            {confirmingDelete ? 'Delete with its payments?' : 'Delete'}
          </button>
          <button className="btn" type="button" onClick={() => setAddition(null)}>
            Add addition
          </button>
        </div>
      </div>
      {remove.error && <p className="form-error project-delete-error">{remove.error.message}</p>}

      <div className="bento project-bento">
        <TimelineTile project={project} />
        <PriceTile project={project} onPay={() => setPaying({ target: null })} />
        <ClientTile project={project} />
        <AdditionsTile
          project={project}
          onAdd={() => setAddition(null)}
          onEdit={setAddition}
          onPay={(target) => setPaying({ target })}
        />
        <PaymentsTile
          project={project}
          onRecord={(target) => setPaying({ target })}
          onOpen={setPayment}
        />
        <MaintenanceTile project={project} />
      </div>

      {editing && (
        <ProjectDialog project={project} onClose={() => setEditing(false)} />
      )}
      {addition !== undefined && (
        <AdditionDialog
          projectId={project.id}
          addition={addition ?? undefined}
          onClose={() => setAddition(undefined)}
        />
      )}
      {paying && (
        <PaymentDialog
          project={project}
          target={paying.target}
          onClose={() => setPaying(undefined)}
        />
      )}
      {payment && (
        <PaymentDialog project={project} payment={payment} onClose={() => setPayment(undefined)} />
      )}
    </>
  )
}

function TimelineTile({ project }: { project: Project }) {
  const left = daysLeft(project)
  const percent = elapsedPercent(project)
  let headline: string
  if (project.delivered_on) headline = 'Delivered'
  else if (left === null) headline = `${plural(daysIn(project), 'day')} in`
  else headline = dueText(left)

  return (
    <section className="tile span-5">
      <h2 className="tile-label">Timeline</h2>
      <p className={`big-number timeline-headline${left !== null && left < 0 && !project.delivered_on ? ' late' : ''}`}>
        {headline}
      </p>
      <div className="timeline-track">
        <Track project={project} />
      </div>
      <dl className="timeline-dates">
        <div>
          <dt>Started</dt>
          <dd>{formatDay(project.started_on, { weekday: true })}</dd>
        </div>
        {project.delivered_on ? (
          <>
            {project.due_on && (
              <div>
                <dt>Due</dt>
                <dd>{formatDay(project.due_on, { weekday: true })}</dd>
              </div>
            )}
            <div>
              <dt>Delivered</dt>
              <dd>{formatDay(project.delivered_on, { weekday: true })}</dd>
            </div>
          </>
        ) : project.due_on ? (
          <>
            <div>
              <dt>Elapsed</dt>
              <dd>{percent}%</dd>
            </div>
            <div>
              <dt>Due</dt>
              <dd>{formatDay(project.due_on, { weekday: true })}</dd>
            </div>
          </>
        ) : (
          <div>
            <dt>Due</dt>
            <dd>No due date</dd>
          </div>
        )}
      </dl>
    </section>
  )
}

function PriceTile({ project, onPay }: { project: Project; onPay: () => void }) {
  const save = useSaveProject(project.id)
  const split = project.expected_deposit > 0 && project.expected_final > 0
  const afterDelivery = project.delivered_on ? 'due now' : 'on delivery'

  return (
    <section className="tile ink span-4">
      <h2 className="tile-label">Project price</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(project.price)}
      </p>
      <div className="price-halves">
        {split ? (
          <>
            <div className={project.deposit_due === 0 ? 'paid' : undefined}>
              <b>{formatNTD(project.expected_deposit)}</b>
              Deposit {project.deposit_percent}% ·{' '}
              {project.deposit_due === 0
                ? 'paid'
                : project.paid > 0
                  ? `${formatNTD(project.deposit_due)} to go`
                  : 'up front'}
            </div>
            <div className={project.outstanding === 0 ? 'paid' : undefined}>
              <b>{formatNTD(project.expected_final)}</b>
              Final ·{' '}
              {project.outstanding === 0
                ? 'paid'
                : project.final_due < project.expected_final
                  ? `${formatNTD(project.final_due)} ${afterDelivery}`
                  : afterDelivery}
            </div>
          </>
        ) : (
          <div className={`whole${project.outstanding === 0 ? ' paid' : ''}`}>
            <b>{formatNTD(project.price)}</b>
            {project.deposit_percent === 100 ? 'Up front' : 'Single payment'} ·{' '}
            {project.outstanding === 0
              ? 'paid'
              : project.deposit_percent === 100
                ? `${formatNTD(project.outstanding)} to go`
                : afterDelivery}
          </div>
        )}
      </div>
      {save.error && <p className="form-error price-error">{save.error.message}</p>}
      <div className="price-action">
        {!project.delivered_on ? (
          <button
            className="btn"
            type="button"
            disabled={save.isPending}
            onClick={() => save.mutate({ ...projectInput(project), delivered_on: todayISO() })}
          >
            Mark delivered
          </button>
        ) : project.outstanding > 0 ? (
          <button className="btn" type="button" onClick={onPay}>
            Record final payment
          </button>
        ) : (
          <p className="price-note">Delivered {formatDay(project.delivered_on, { year: true })} · paid in full</p>
        )}
      </div>
    </section>
  )
}

function ClientTile({ project }: { project: Project }) {
  const client = useClient(project.client.id)
  const { name, contact_person, avatar_url } = project.client

  return (
    <section className="tile span-3 tint-lavender">
      <div className="tile-head">
        <h2 className="tile-label">Client</h2>
        <Link className="link-btn" to={`/clients/${project.client.id}`}>
          Open
        </Link>
      </div>
      <div className="project-client">
        <Avatar className="project-client-avatar" src={avatar_url} fallback={initials(contact_person ?? name)} />
        <div>
          <b>{contact_person ?? name}</b>
          {contact_person && <small>{name}</small>}
        </div>
      </div>
      {client.data && client.data.contacts.length > 0 && (
        <ul className="project-client-contacts">
          {client.data.contacts.map((contact) => (
            <li key={contact.id}>
              <span>
                <KindLabel kind={contact.kind} />
              </span>
              <b>{contactHandle(contact)}</b>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

type AdditionsProps = {
  project: Project
  onAdd: () => void
  onEdit: (addition: Addition) => void
  onPay: (target: Target) => void
}

function AdditionsTile({ project, onAdd, onEdit, onPay }: AdditionsProps) {
  return (
    <section className="tile span-7">
      <div className="tile-head">
        <h2 className="tile-label">Additions</h2>
        <button className="link-btn" type="button" onClick={onAdd}>
          Add addition
        </button>
      </div>
      {project.additions.length === 0 ? (
        <p className="empty-note">
          No additions yet. Extra features the client asks for, even after delivery, go here.
        </p>
      ) : (
        <ul className="addition-list">
          {project.additions.map((addition) => (
            <AdditionRow
              key={addition.id}
              projectId={project.id}
              addition={addition}
              onEdit={() => onEdit(addition)}
              onPay={() => onPay(addition.id)}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

type AdditionRowProps = {
  projectId: number
  addition: Addition
  onEdit: () => void
  onPay: () => void
}

function AdditionRow({ projectId, addition, onEdit, onPay }: AdditionRowProps) {
  const save = useSaveAddition(projectId, addition.id)
  const [day, month] = formatDay(addition.agreed_on).split(' ')

  return (
    <li className="addition-row">
      <span className="addition-date" title={`Agreed ${formatDay(addition.agreed_on, { year: true })}`}>
        <b>{day}</b>
        {month}
      </span>
      <div className="addition-body">
        <b>{addition.name}</b>
        {addition.description && <small>{addition.description}</small>}
        <ul className="terms">
          {terms(addition).map((term) => (
            <li key={term.label} className={term.tone}>
              {term.label}
            </li>
          ))}
        </ul>
        <div className="addition-actions">
          <button className="link-btn" type="button" onClick={onEdit}>
            Edit
          </button>
          {!addition.delivered_on && (
            <button
              className="link-btn"
              type="button"
              disabled={save.isPending}
              onClick={() => save.mutate({ ...additionInput(addition), delivered_on: todayISO() })}
            >
              Mark delivered
            </button>
          )}
          {addition.outstanding > 0 && (
            <button className="link-btn" type="button" onClick={onPay}>
              Record payment
            </button>
          )}
        </div>
        {save.error && <p className="form-error">{save.error.message}</p>}
      </div>
      <span className="addition-amount">{formatNTD(addition.price)}</span>
    </li>
  )
}

/** Payment-terms chips, e.g. "50% deposit paid" + "NT$4,000 on delivery". */
function terms(addition: Addition): { label: string; tone: 'paid' | 'due' | '' }[] {
  const out: { label: string; tone: 'paid' | 'due' | '' }[] = []
  if (addition.expected_deposit > 0 && addition.expected_final > 0) {
    const pct = addition.deposit_percent
    out.push(
      addition.deposit_due === 0
        ? { label: `${pct}% deposit paid`, tone: 'paid' }
        : { label: `${pct}% deposit · ${formatNTD(addition.deposit_due)} due`, tone: 'due' },
    )
    if (addition.final_due === 0) out.push({ label: 'Rest paid', tone: 'paid' })
    else if (addition.delivered_on) out.push({ label: `${formatNTD(addition.final_due)} due`, tone: 'due' })
    else out.push({ label: `${formatNTD(addition.final_due)} on delivery`, tone: '' })
  } else {
    out.push({ label: addition.deposit_percent === 100 ? 'Up front' : 'Single payment', tone: '' })
    out.push(addition.outstanding === 0 ? { label: 'Paid', tone: 'paid' } : { label: 'Unpaid', tone: 'due' })
  }
  if (addition.delivered_on) out.push({ label: `Delivered ${formatDay(addition.delivered_on)}`, tone: '' })
  return out
}

type Upcoming = { key: string; target: Target; label: string; when: string; amount: number }

/** Money still to come, per target: what's left of the deposit, then the rest. */
function upcoming(project: Project): Upcoming[] {
  const targets: (Billing & { id: Target; name: string; delivered_on: string | null })[] = [
    { ...project, id: null, name: 'Project' },
    ...project.additions,
  ]
  return targets.flatMap((t) => {
    const key = String(t.id ?? 'project')
    const afterDelivery = t.delivered_on ? 'Due now' : 'On delivery'
    if (t.outstanding === 0) return []
    if (t.expected_deposit === 0 || t.expected_final === 0) {
      const when = t.expected_final === 0 ? 'Up front' : t.delivered_on ? 'Due now' : 'Single payment'
      return [{ key, target: t.id, label: t.name, when, amount: t.outstanding }]
    }
    const rows: Upcoming[] = []
    if (t.deposit_due > 0) {
      rows.push({ key: `${key}-deposit`, target: t.id, label: `${t.name} deposit`, when: 'Up front', amount: t.deposit_due })
    }
    if (t.final_due > 0) {
      const label = t.id === null ? 'Project final payment' : `${t.name}, rest`
      rows.push({ key: `${key}-final`, target: t.id, label, when: afterDelivery, amount: t.final_due })
    }
    return rows
  })
}

type PaymentsProps = {
  project: Project
  onRecord: (target: Target) => void
  onOpen: (payment: Payment) => void
}

function PaymentsTile({ project, onRecord, onOpen }: PaymentsProps) {
  const toCome = upcoming(project)

  return (
    <section className="tile span-5 tint-sage">
      <div className="tile-head">
        <h2 className="tile-label">Payments</h2>
        {project.total_outstanding > 0 && (
          <button className="link-btn" type="button" onClick={() => onRecord(null)}>
            Record
          </button>
        )}
      </div>
      {project.payments.length === 0 && <p className="empty-note">No payments yet.</p>}
      <ul className="pay-list">
        {project.payments.map((payment) => (
          <li key={payment.id}>
            <button className="pay-row" type="button" onClick={() => onOpen(payment)}>
              <span>
                {paymentLabel(project, payment)}
                <small>
                  {formatDay(payment.paid_on)}
                  {payment.note && ` · ${payment.note}`}
                </small>
              </span>
              <b>{formatNTD(payment.amount)}</b>
            </button>
          </li>
        ))}
      </ul>
      {toCome.length > 0 && (
        <>
          <h3 className="pay-subhead">Still to come</h3>
          <ul className="pay-list">
            {toCome.map((row) => (
              <li key={row.key}>
                <button
                  className="pay-row next"
                  type="button"
                  aria-label={`Record ${row.label}, ${formatNTD(row.amount)}`}
                  onClick={() => onRecord(row.target)}
                >
                  <span>
                    {row.label}
                    <small>{row.when}</small>
                  </span>
                  <b>{formatNTD(row.amount)}</b>
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <p className="pay-sum">
        <span>
          Received <b>{formatNTD(project.total_paid)}</b>
        </span>
        <span>
          Outstanding <b>{formatNTD(project.total_outstanding)}</b>
        </span>
      </p>
    </section>
  )
}

/** Span-12 lavender tile: every client paying a monthly fee for this project, whoever's it is. */
function MaintenanceTile({ project }: { project: Project }) {
  const retainers = useProjectRetainers(project.id)
  // undefined = closed, null = adding, a retainer = editing it.
  const [dialog, setDialog] = useState<Retainer | null>()
  const [opened, setOpened] = useState<{ retainer: Retainer; month: Month }>()
  const active = retainers.data?.filter((r) => r.active) ?? []
  const clients = new Set(active.map((r) => r.client.id)).size
  const monthly = active.reduce((sum, r) => sum + r.amount, 0)

  return (
    <section className="tile span-12 tint-lavender project-retainers">
      <div className="tile-head">
        <h2 className="tile-label">Maintenance</h2>
        <button className="link-btn" type="button" onClick={() => setDialog(null)}>
          Add retainer
        </button>
      </div>
      {retainers.error && <p className="empty-note">Couldn't load maintenance: {retainers.error.message}</p>}
      {retainers.data?.length === 0 && (
        <p className="empty-note">
          No monthly fees for this project. Add a retainer for each client who pays monthly to use it.
        </p>
      )}
      {active.length > 0 && (
        <p className="project-retainer-sum">
          {plural(clients, 'client')} paying · <b>{formatNTD(monthly)}</b> per month
        </p>
      )}
      {retainers.data && retainers.data.length > 0 && (
        <ul className="project-retainer-list">
          {retainers.data.map((retainer) => (
            <RetainerRow
              key={retainer.id}
              retainer={retainer}
              onEdit={() => setDialog(retainer)}
              onMonth={(month) => setOpened({ retainer, month })}
            />
          ))}
        </ul>
      )}
      {dialog !== undefined && (
        <RetainerDialog
          retainer={dialog ?? undefined}
          projectId={project.id}
          onClose={() => setDialog(undefined)}
        />
      )}
      {opened && <MonthDialog {...opened} onClose={() => setOpened(undefined)} />}
    </section>
  )
}

type RetainerRowProps = { retainer: Retainer; onEdit: () => void; onMonth: (month: Month) => void }

function RetainerRow({ retainer, onEdit, onMonth }: RetainerRowProps) {
  const { client } = retainer
  const chip = monthChip(retainer, todayISO())
  const month = retainer.this_month

  return (
    <li className={`project-retainer${retainer.active ? '' : ' ended'}`}>
      <Avatar
        className={`project-retainer-avatar ${tintClass(client.id)}`}
        aria-hidden="true"
        src={client.avatar_url}
        fallback={initials(client.name)}
      />
      <div className="project-retainer-name">
        <Link to={`/clients/${client.id}`}>{client.name}</Link>
        <small>
          {scheduleText(retainer)} ·{' '}
          <button className="link-btn" type="button" onClick={onEdit}>
            Edit
          </button>
        </small>
      </div>
      <span className="project-retainer-amount">
        {formatNTD(retainer.amount)}
        <small>/mo</small>
      </span>
      {retainer.collection === 'ask' && month ? (
        <button
          className={`chip project-retainer-status ${chip.tone}`}
          type="button"
          title={month.status === 'paid' ? 'View payment' : 'Record payment'}
          onClick={() => onMonth(month)}
        >
          {chip.label}
        </button>
      ) : (
        <span className={`chip project-retainer-status ${chip.tone}`}>{chip.label}</span>
      )}
    </li>
  )
}
