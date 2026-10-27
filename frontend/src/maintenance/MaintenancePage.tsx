import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router'
import { contactHandle, contactKinds, contactUrl } from '../clients/contactKinds.ts'
import { KindLabel } from '../clients/KindLabel.tsx'
import { MessageLink } from '../clients/MessageLink.tsx'
import { AddButton } from '../components/AddButton.tsx'
import { Avatar } from '../components/Avatar.tsx'
import { Dialog, type DialogHandle } from '../components/Dialog.tsx'
import { daysBetween, formatDay, formatNTD, formatNumber, initials, parseDate, plural } from '../format.ts'
import { tintClass } from '../tint.ts'
import { findMonth, monthName, monthStatusChip, ordinal, periodChip, scheduleText } from './labels.ts'
import {
  useMaintenance,
  type CalendarDay,
  type Maintenance,
  type Month,
  type Overdue,
  type Retainer,
} from './queries.ts'
import { RetainerDialog } from './RetainerDialog.tsx'
import { MonthDialog } from './RetainerPaymentDialog.tsx'
import { useRecordPayment } from './useRecordPayment.tsx'
import './MaintenancePage.css'

/** "2026-11" for the month `count` months from an ISO date's month. */
function shiftMonth(iso: string, count: number): string {
  const date = parseDate(iso)
  const shifted = new Date(date.getFullYear(), date.getMonth() + count, 1)
  return `${shifted.getFullYear()}-${String(shifted.getMonth() + 1).padStart(2, '0')}`
}

type Opened = { retainer: Retainer; month: Month }

export function MaintenancePage() {
  // null shows this month in the calendar.
  const [month, setMonth] = useState<string | null>(null)
  const maintenance = useMaintenance(month)
  const [adding, setAdding] = useState(false)
  const data = maintenance.data
  const linked = useLinkedMonth(data)
  const { hash } = useLocation()
  const loaded = data !== undefined

  // Links such as /maintenance#overdue land on their tile once it renders.
  useEffect(() => {
    if (loaded && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [loaded, hash])

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Retainers</h1>
          {data && (
            <p className="page-sub">
              {plural(data.active_count, 'retainer')} · {formatNTD(data.monthly_total)} per month
            </p>
          )}
        </div>
        <div className="page-actions">
          <AddButton label="Add retainer" onClick={() => setAdding(true)} />
        </div>
      </div>

      {maintenance.isPending && <p className="status">Loading retainers…</p>}
      {maintenance.error && <p className="status">Couldn't load retainers: {maintenance.error.message}</p>}

      {data && (
        <div className="bento">
          <OverdueTile data={data} />
          <NextReminderTile data={data} />
          <CollectedTile data={data} />
          <AutomaticTile data={data} />
          {/* The calendar and, under it, the overdue list share the left column. */}
          <div className="span-5 mt-side">
            <CalendarTile
              data={data}
              onMonth={(count) => {
                const next = shiftMonth(data.month, count)
                setMonth(next === data.today.slice(0, 7) ? null : next)
              }}
              onToday={() => setMonth(null)}
            />
            <OverdueListTile data={data} />
          </div>
          <RetainersTile data={data} />
        </div>
      )}

      {adding && <RetainerDialog onClose={() => setAdding(false)} />}
      {linked.opened && <MonthDialog {...linked.opened} onClose={linked.close} />}
    </>
  )
}

/**
 * The month a reminder's Record payment link opens, from ?record=<retainer id>&month=YYYY-MM.
 * Read once, when the data arrives, and dropped from the address so a reload doesn't reopen it.
 */
function useLinkedMonth(data: Maintenance | undefined) {
  const [params, setParams] = useSearchParams()
  const [link, setLink] = useState(() =>
    params.has('record') ? { id: Number(params.get('record')), period: `${params.get('month')}-01` } : null,
  )
  const [opened, setOpened] = useState<Opened>()

  // Resolved once, so the dialog keeps the month it opened with while a payment refetches.
  if (link && data) {
    const retainer = data.retainers.find((r) => r.id === link.id)
    const month = retainer && findMonth(retainer, link.period)
    setLink(null)
    if (retainer && month) setOpened({ retainer, month })
  }

  useEffect(() => {
    if (params.has('record')) setParams({}, { replace: true })
  }, [params, setParams])

  return { opened, close: () => setOpened(undefined) }
}

/** "Aug, Sep, Oct" */
const monthList = (periods: string[]) => [...new Set(periods.map((p) => monthName(p)))].join(', ')

/** The client overdue the longest, with everything they owe past the grace days. */
function OverdueTile({ data }: { data: Maintenance }) {
  const [dialog, record] = useRecordPayment()
  const [worst] = data.overdue
  const retainer = data.retainers.find((r) => r.id === worst?.retainer_id)
  const theirs = data.overdue.filter((o) => o.client.id === worst?.client.id)
  const others = new Set(data.overdue.map((o) => o.client.id)).size - (worst ? 1 : 0)
  const reminded = worst?.last_reminded_on

  let meta = 'Nothing overdue'
  if (worst) {
    meta = `${worst.client.name} · ${reminded ? `reminded ${formatDay(reminded)}` : monthList(theirs.map((o) => o.period))}`
    if (others) meta += ` · ${plural(others, 'more client')}`
  }

  return (
    <section className="tile span-3 tint-peach mt-summary">
      <h2 className="tile-label">{worst ? `Overdue · ${plural(worst.days, 'day')}` : 'Overdue'}</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(theirs.reduce((sum, o) => sum + o.amount, 0))}
      </p>
      <p className="mt-meta">{meta}</p>
      {worst && retainer && (
        <div className="mt-action">
          <button className="btn" type="button" onClick={() => record(retainer, worst.period)}>
            Record payment
          </button>
          <MessageLink contact={retainer.ask_via} />
        </div>
      )}
      {dialog}
    </section>
  )
}

function NextReminderTile({ data }: { data: Maintenance }) {
  const [dialog, record] = useRecordPayment()
  const next = data.next_reminder
  // The retainer of the oldest month it asks for, which Record payment opens.
  const retainer =
    next &&
    data.retainers.find((r) => {
      const month = findMonth(r, next.periods[0])
      return r.client.id === next.client.id && month !== undefined && month.status !== 'paid'
    })
  let when = 'None'
  if (next) {
    const day = next.at.slice(0, 10)
    const days = daysBetween(data.today, day)
    const weekday = parseDate(day).toLocaleDateString('en-US', { weekday: 'short' })
    if (next.pending) when = 'Now'
    else if (days < 7) when = `${days === 0 ? 'Today' : weekday} ${next.at.slice(11, 16)}`
    else when = formatDay(day)
  }

  return (
    <section className="tile span-3 ink mt-summary">
      <h2 className="tile-label">Next reminder</h2>
      <p className="big-number">{when}</p>
      <p className="mt-meta">
        {next
          ? `${next.client.name} · ${formatNTD(next.amount)} · ${monthList(next.periods)}`
          : 'No ask retainers are waiting'}
        {next?.last_reminded_on === data.today && ' · reminded today'}
        {next?.pending && !data.reminders.enabled && ' · reminders are off'}
      </p>
      {next && retainer && (
        <div className="mt-action">
          <button className="btn" type="button" onClick={() => record(retainer, next.periods[0])}>
            Record payment
          </button>
          <MessageLink contact={retainer.ask_via} />
        </div>
      )}
      {dialog}
    </section>
  )
}

function CollectedTile({ data }: { data: Maintenance }) {
  const { received, expected, paid, count, period } = data.collected
  const percent = expected ? Math.round((received / expected) * 100) : 0

  return (
    <section className="tile span-3 tint-sage mt-summary">
      <h2 className="tile-label">Collected in {monthName(period, true)}</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(received)}
        <small className="mt-of"> of {formatNTD(expected)}</small>
      </p>
      <p className="mt-meta">{count ? `${paid} of ${count} paid` : 'Nothing billed this month'}</p>
      <div
        className="track mt-bar"
        role="progressbar"
        aria-label="Collected this month"
        aria-valuenow={Math.min(percent, 100)}
      >
        <i className="good" style={{ width: `${Math.min(percent, 100)}%` }} />
      </div>
    </section>
  )
}

function AutomaticTile({ data }: { data: Maintenance }) {
  const { amount, clients } = data.automatic
  return (
    <section className="tile span-3 tint-lavender mt-summary">
      <h2 className="tile-label">Automatic</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(amount)}
        <small>/mo</small>
      </p>
      <p className="mt-meta">
        {clients
          ? `${plural(clients, 'client')} ${clients === 1 ? 'pays' : 'pay'} by bank transfer, so they get no reminders`
          : 'No one pays by automatic transfer yet'}
      </p>
    </section>
  )
}

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

type CalendarProps = { data: Maintenance; onMonth: (count: number) => void; onToday: () => void }

function CalendarTile({ data, onMonth, onToday }: CalendarProps) {
  const first = parseDate(data.month)
  const lead = (first.getDay() + 6) % 7 // Monday first
  const length = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  const byDay = new Map(data.calendar.map((d) => [d.day, d]))
  const thisMonth = data.today.slice(0, 7) === data.month.slice(0, 7)
  const title = first.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
  // A day with several months due picks one first; one month opens straight away.
  const [picking, setPicking] = useState<{ day: string; items: Opened[] }>()
  const [opened, setOpened] = useState<Opened>()

  return (
    <section className="tile">
      <div className="tile-head">
        <div className="mt-cal-nav">
          <button className="mt-arrow" type="button" aria-label="Previous month" onClick={() => onMonth(-1)}>
            ‹
          </button>
          <h2 className="mt-title">{title}</h2>
          <button className="mt-arrow" type="button" aria-label="Next month" onClick={() => onMonth(1)}>
            ›
          </button>
        </div>
        {thisMonth ? (
          <span className="tile-label">Today is the {ordinal(parseDate(data.today).getDate())}</span>
        ) : (
          <button className="link-btn" type="button" onClick={onToday}>
            Back to today
          </button>
        )}
      </div>
      <div className="mt-cal">
        {WEEKDAYS.map((d) => (
          <abbr key={d} className="mt-dow" title={d}>
            {d[0]}
          </abbr>
        ))}
        {Array.from({ length: lead }, (_, i) => (
          <span key={`lead-${i}`} />
        ))}
        {Array.from({ length: length }, (_, i) => {
          const day = `${data.month.slice(0, 8)}${String(i + 1).padStart(2, '0')}`
          const items = dueMonths(byDay.get(day), data)
          return (
            <CalendarCell
              key={day}
              day={day}
              entry={byDay.get(day)}
              today={day === data.today}
              onOpen={items.length ? () => (items.length === 1 ? setOpened(items[0]) : setPicking({ day, items })) : undefined}
            />
          )
        })}
      </div>
      <div className="mt-legend" aria-hidden="true">
        <span>
          <i className="paid" />
          Paid
        </span>
        <span>
          <i className="overdue" />
          Overdue
        </span>
        <span>
          <i className="upcoming" />
          Due
        </span>
      </div>
      {picking && (
        <DayDialog {...picking} today={data.today} onPick={setOpened} onClose={() => setPicking(undefined)} />
      )}
      {opened && <MonthDialog {...opened} onClose={() => setOpened(undefined)} />}
    </section>
  )
}

/** The "ask" months due on a calendar day, each opening its payment. Auto transfers need nothing. */
function dueMonths(entry: CalendarDay | undefined, data: Maintenance): Opened[] {
  if (!entry) return []
  return entry.entries.flatMap((e) => {
    const retainer = data.retainers.find((r) => r.id === e.retainer_id)
    const month = data.months[e.retainer_id]
    return retainer && month && canOpen(retainer, month) ? [{ retainer, month }] : []
  })
}

/**
 * Whether a month opens its payment: "ask" retainers only. A paid month shows its payment; an
 * unpaid one opens Record payment, which can only offer the months it knows.
 */
function canOpen(retainer: Retainer, month: Month): boolean {
  if (retainer.collection !== 'ask') return false
  return month.status === 'paid' || findMonth(retainer, month.period) !== undefined
}

type CellProps = { day: string; entry?: CalendarDay; today: boolean; onOpen?: () => void }

function CalendarCell({ day, entry, today, onOpen }: CellProps) {
  const date = parseDate(day).getDate()
  const classes = ['mt-day', entry?.status, today && 'today'].filter(Boolean).join(' ')
  const label = entry
    ? `${formatDay(day)}: ${entry.entries.map((e) => `${e.client.name} ${formatNTD(e.amount)} ${e.status}`).join(', ')}`
    : undefined
  if (onOpen) {
    return (
      <button className={classes} type="button" title={label} aria-label={label} aria-current={today ? 'date' : undefined} onClick={onOpen}>
        {date}
      </button>
    )
  }
  return (
    <span className={classes} title={label} aria-label={label} aria-current={today ? 'date' : undefined}>
      {date}
    </span>
  )
}

type DayProps = { day: string; items: Opened[]; today: string; onPick: (item: Opened) => void; onClose: () => void }

/** Several months due on one day: pick whose payment to record or view. */
function DayDialog({ day, items, today, onPick, onClose }: DayProps) {
  const dialog = useRef<DialogHandle>(null)

  return (
    <Dialog title={`Due ${formatDay(day, { weekday: true })}`} ref={dialog} onClose={onClose}>
      <ul className="mt-day-list">
        {items.map((item) => {
          const { retainer, month } = item
          const chip = monthStatusChip(month, retainer, today)
          return (
            <li key={retainer.id}>
              <button
                className="mt-day-row"
                type="button"
                onClick={() => {
                  onPick(item)
                  dialog.current?.close()
                }}
              >
                <Avatar
                  className={`mt-avatar ${tintClass(retainer.client.id)}`}
                  aria-hidden="true"
                  src={retainer.client.avatar_url}
                  fallback={initials(retainer.client.name)}
                />
                <b>{retainer.client.name}</b>
                <span className="mt-amount">{formatNTD(month.amount)}</span>
                {/* "Due Sun" would only repeat the title. */}
                {(chip.tone === 'ok' || chip.tone === 'late' || month.status === 'unpaid') && (
                  <span className={`chip mt-status ${chip.tone}`}>{chip.label}</span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </Dialog>
  )
}

/** Every retainer with months unpaid past the grace days, from any month, longest overdue first. */
function OverdueListTile({ data }: { data: Maintenance }) {
  const [dialog, record] = useRecordPayment()
  // Kept while the last payment's dialog closes.
  if (!data.overdue.length) return dialog || null

  const byRetainer = new Map<number, Overdue[]>()
  for (const o of data.overdue) byRetainer.set(o.retainer_id, [...(byRetainer.get(o.retainer_id) ?? []), o])
  const total = data.overdue.reduce((sum, o) => sum + o.amount, 0)

  return (
    <section className="tile" id="overdue">
      <div className="tile-head">
        <h2 className="mt-title">Overdue</h2>
        <span className="tile-label">
          {plural(data.overdue.length, 'month')} · {formatNTD(total)}
        </span>
      </div>
      <ul className="mt-rows">
        {[...byRetainer].map(([id, months]) => {
          const retainer = data.retainers.find((r) => r.id === id)
          if (!retainer) return null
          const [oldest] = months
          return (
            <li key={id} className="mt-row mt-owed">
              <Link className="mt-avatar-link" to={`/clients/${retainer.client.id}`} aria-label={`Open ${retainer.client.name}`}>
                <Avatar
                  className={`mt-avatar ${tintClass(retainer.client.id)}`}
                  src={retainer.client.avatar_url}
                  fallback={initials(retainer.client.name)}
                />
              </Link>
              <div className="mt-owed-name">
                <b>
                  <Link to={`/clients/${retainer.client.id}`}>{retainer.client.name}</Link>
                </b>
                <small>
                  {retainer.project && (
                    <>
                      <Link to={`/projects/${retainer.project.id}`}>{retainer.project.name}</Link> ·{' '}
                    </>
                  )}
                  {monthList(months.map((o) => o.period))}
                </small>
              </div>
              <span className="mt-amount">{formatNTD(months.reduce((sum, o) => sum + o.amount, 0))}</span>
              <button
                className="chip mt-status late"
                type="button"
                title="Record payment"
                onClick={() => record(retainer, oldest.period)}
              >
                Overdue {oldest.days}d
              </button>
            </li>
          )
        })}
      </ul>
      {dialog}
    </section>
  )
}

function RetainersTile({ data }: { data: Maintenance }) {
  const [editing, setEditing] = useState<Retainer>()
  const [opened, setOpened] = useState<Opened>()
  const thisMonth = data.today.slice(0, 7) === data.month.slice(0, 7)

  return (
    <section className="tile span-7">
      <div className="tile-head">
        <h2 className="mt-title">Retainers</h2>
        <span className="tile-label">
          {thisMonth
            ? 'This month'
            : parseDate(data.month).toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
        </span>
      </div>
      {data.retainers.length === 0 && (
        <p className="empty-note">No retainers yet. Add one for a client's monthly maintenance.</p>
      )}
      <ul className="mt-rows">
        {data.retainers.map((retainer) => (
          <RetainerRow
            key={retainer.id}
            retainer={retainer}
            month={data.months[retainer.id]}
            period={data.month}
            today={data.today}
            onEdit={() => setEditing(retainer)}
            onMonth={(month) => setOpened({ retainer, month })}
          />
        ))}
      </ul>
      {editing && <RetainerDialog retainer={editing} onClose={() => setEditing(undefined)} />}
      {opened && <MonthDialog {...opened} onClose={() => setOpened(undefined)} />}
    </section>
  )
}

type RowProps = {
  retainer: Retainer
  /** In the calendar's month, if billed then. */
  month?: Month
  period: string
  today: string
  onEdit: () => void
  onMonth: (month: Month) => void
}

function RetainerRow({ retainer, month, period, today, onEdit, onMonth }: RowProps) {
  const chip = periodChip(retainer, month, period, today)
  const actionable = month !== undefined && canOpen(retainer, month)
  const contact = retainer.ask_via
  const url = contact && contactUrl(contact)

  return (
    <li className={`mt-row${retainer.active ? '' : ' ended'}`}>
      <Link className="mt-avatar-link" to={`/clients/${retainer.client.id}`} aria-label={`Open ${retainer.client.name}`}>
        <Avatar
          className={`mt-avatar ${tintClass(retainer.client.id)}`}
          src={retainer.client.avatar_url}
          fallback={initials(retainer.client.name)}
        />
      </Link>
      <div className="mt-name">
        <button type="button" onClick={onEdit} aria-label={`Edit ${retainer.client.name} retainer`}>
          <b>{retainer.client.name}</b>
        </button>
        <small>
          {retainer.project && (
            <>
              <Link to={`/projects/${retainer.project.id}`}>{retainer.project.name}</Link> ·{' '}
            </>
          )}
          {scheduleText(retainer, { contact: false })}
        </small>
      </div>
      <span className="mt-amount">{formatNTD(retainer.amount)}</span>
      {retainer.collection === 'auto_transfer' ? (
        <span className="chip good mt-contact">Auto transfer</span>
      ) : contact && url ? (
        // The platform says how you ask; the link opens the conversation.
        <a
          className={`chip mt-contact mt-link kind-${contact.kind}`}
          href={url}
          target={url.startsWith('https:') ? '_blank' : undefined}
          rel="noreferrer"
          title={`${contactKinds[contact.kind].message}: ${contactHandle(contact)}`}
        >
          <KindLabel kind={contact.kind} />
          <svg className="mt-link-arrow" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 17 17 7" />
            <path d="M8 7h9v9" />
          </svg>
        </a>
      ) : contact ? (
        <span className="chip mt-contact" title={contactHandle(contact)}>
          <KindLabel kind={contact.kind} /> {contactHandle(contact)}
        </span>
      ) : (
        <span className="chip mt-contact">No contact</span>
      )}
      {actionable ? (
        <button
          className={`chip mt-status ${chip.tone}`}
          type="button"
          title={month.status === 'paid' ? 'View payment' : 'Record payment'}
          onClick={() => onMonth(month)}
        >
          {chip.label}
        </button>
      ) : (
        <span className={`chip mt-status ${chip.tone}`}>{chip.label}</span>
      )}
    </li>
  )
}
