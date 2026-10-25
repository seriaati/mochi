import { useState } from 'react'
import { Link } from 'react-router'
import { contactKinds } from '../clients/contactKinds.ts'
import type { Client } from '../clients/queries.ts'
import { formatDay, formatNumber, parseDate, todayISO } from '../format.ts'
import { dueLabel, monthName, ordinal } from './labels.ts'
import { useClientRetainers, type Month, type Retainer } from './queries.ts'
import { RetainerDialog } from './RetainerDialog.tsx'
import { MonthDialog } from './RetainerPaymentDialog.tsx'
import './ClientMaintenanceTile.css'

/** Span-12 lavender tile on the client page: each retainer with its recent months. */
export function ClientMaintenanceTile({ client }: { client: Client }) {
  const retainers = useClientRetainers(client.id)
  // undefined = closed, null = adding, a retainer = editing it.
  const [dialog, setDialog] = useState<Retainer | null>()
  const [opened, setOpened] = useState<{ retainer: Retainer; month: Month }>()

  return (
    <section className="tile span-12 tint-lavender">
      <div className="tile-head">
        <h2 className="tile-label">Maintenance</h2>
        <button className="link-btn" type="button" onClick={() => setDialog(null)}>
          Add retainer
        </button>
      </div>
      {retainers.error && <p className="empty-note">Couldn't load maintenance: {retainers.error.message}</p>}
      {retainers.data?.length === 0 && (
        <p className="empty-note">No monthly maintenance for this client.</p>
      )}
      {retainers.data?.map((retainer) => (
        <RetainerSummary
          key={retainer.id}
          retainer={retainer}
          onEdit={() => setDialog(retainer)}
          onMonth={(month) => setOpened({ retainer, month })}
        />
      ))}
      {dialog !== undefined && (
        <RetainerDialog retainer={dialog ?? undefined} clientId={client.id} onClose={() => setDialog(undefined)} />
      )}
      {opened && <MonthDialog {...opened} onClose={() => setOpened(undefined)} />}
    </section>
  )
}

function describe(retainer: Retainer): string {
  const parts = [`Due on the ${ordinal(retainer.due_day)}`]
  if (retainer.collection === 'auto_transfer') parts.push('paid by automatic bank transfer')
  else {
    parts.push(retainer.ask_via ? `you ask on ${contactKinds[retainer.ask_via.kind].label}` : 'you ask')
    parts.push('reminder at 09:00 on the due date')
  }
  if (retainer.ended_on && !retainer.active) {
    const past = retainer.ended_on < todayISO()
    parts.push(past ? `ended ${formatDay(retainer.ended_on, { year: true })}` : `ends ${formatDay(retainer.ended_on)}`)
  } else if (!retainer.active) parts.push(`starts ${formatDay(retainer.started_on)}`)
  return parts.join(' · ')
}

type SummaryProps = { retainer: Retainer; onEdit: () => void; onMonth: (month: Month) => void }

function RetainerSummary({ retainer, onEdit, onMonth }: SummaryProps) {
  return (
    <div className="client-retainer">
      <div>
        <p className="big-number">
          <small>NT$</small>
          {formatNumber(retainer.amount)}
          <small>/mo</small>
        </p>
        <p className="client-retainer-text">
          {retainer.project && (
            <>
              For <Link to={`/projects/${retainer.project.id}`}>{retainer.project.name}</Link> ·{' '}
            </>
          )}
          {describe(retainer)}{' '}
          <button className="link-btn" type="button" onClick={onEdit}>
            Edit
          </button>
        </p>
      </div>
      {retainer.months.length > 0 && (
        <ul className="client-months" aria-label="Recent months">
          {retainer.months.map((month) => (
            <li key={month.period}>
              <MonthChip retainer={retainer} month={month} onOpen={() => onMonth(month)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function MonthChip({ retainer, month, onOpen }: { retainer: Retainer; month: Month; onOpen: () => void }) {
  let text = dueLabel(month.due_on)
  if (month.status === 'overdue') text = `${month.days_late}d late`
  if (month.status === 'paid' && month.paid_on) {
    const sameMonth = month.paid_on.slice(0, 7) === month.period.slice(0, 7)
    text = `Paid ${sameMonth ? ordinal(parseDate(month.paid_on).getDate()) : formatDay(month.paid_on)}`
  }
  // Still to collect (upcoming, or due within its grace days) is outlined; late is peach.
  const open = month.status === 'upcoming' || month.status === 'due'
  const tone = open ? 'next' : month.late ? 'late' : ''
  const body = (
    <>
      <b>{monthName(month.period)}</b>
      {text}
    </>
  )
  // Auto transfers need no action; "ask" months open their payment.
  if (retainer.collection !== 'ask') return <span className={`client-month ${tone}`}>{body}</span>
  return (
    <button
      className={`client-month ${tone}`}
      type="button"
      title={month.status === 'paid' ? 'View payment' : 'Record payment'}
      onClick={onOpen}
    >
      {body}
    </button>
  )
}
