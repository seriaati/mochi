import { useState } from 'react'
import { Link } from 'react-router'
import { contactHandle, contactKinds } from '../clients/contactKinds.ts'
import { Avatar } from '../components/Avatar.tsx'
import { daysBetween, formatDay, formatNTD, formatNumber, initials, parseDate, plural } from '../format.ts'
import { tintClass } from '../tint.ts'
import { monthChip, monthName, ordinal, scheduleText } from './labels.ts'
import {
  useMaintenance,
  useRemindClient,
  useSendTest,
  type CalendarDay,
  type Maintenance,
  type Month,
  type Retainer,
} from './queries.ts'
import { RetainerDialog } from './RetainerDialog.tsx'
import { MonthDialog } from './RetainerPaymentDialog.tsx'
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

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Maintenance</h1>
          {data && (
            <p className="page-sub">
              {plural(data.active_count, 'retainer')} · {formatNTD(data.monthly_total)} per month
            </p>
          )}
        </div>
        <div className="page-actions">
          <button className="btn" type="button" onClick={() => setAdding(true)}>
            Add retainer
          </button>
        </div>
      </div>

      {maintenance.isPending && <p className="status">Loading maintenance…</p>}
      {maintenance.error && <p className="status">Couldn't load maintenance: {maintenance.error.message}</p>}

      {data && (
        <div className="bento">
          <OverdueTile data={data} />
          <NextReminderTile data={data} />
          <CollectedTile data={data} />
          <AutomaticTile data={data} />
          <CalendarTile
            data={data}
            onMonth={(count) => {
              const next = shiftMonth(data.month, count)
              setMonth(next === data.today.slice(0, 7) ? null : next)
            }}
            onToday={() => setMonth(null)}
          />
          <RetainersTile data={data} />
          <RemindersTile data={data} />
        </div>
      )}

      {adding && <RetainerDialog onClose={() => setAdding(false)} />}
    </>
  )
}

/** The note under a reminder button: what was sent, or why it failed. */
export function SendResult({ mutation }: { mutation: { error: Error | null; isSuccess: boolean } }) {
  if (mutation.error) return <p className="mt-sent error">{mutation.error.message}</p>
  if (mutation.isSuccess) return <p className="mt-sent">Sent to Discord</p>
  return null
}

/** "Aug, Sep, Oct" */
const monthList = (periods: string[]) => [...new Set(periods.map((p) => monthName(p)))].join(', ')

/** The client overdue the longest, with everything they owe past the grace days. */
function OverdueTile({ data }: { data: Maintenance }) {
  const remind = useRemindClient()
  const [worst] = data.overdue
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
      {worst && (
        <div className="mt-action">
          <button
            className="btn"
            type="button"
            disabled={!data.reminders.enabled || remind.isPending}
            title={data.reminders.enabled ? `Remind ${worst.client.name} on Discord` : 'Reminders are off'}
            onClick={() => remind.mutate(worst.client.id)}
          >
            {reminded ? 'Ping again' : 'Ping now'}
          </button>
          <SendResult mutation={remind} />
        </div>
      )}
    </section>
  )
}

function NextReminderTile({ data }: { data: Maintenance }) {
  const remind = useRemindClient()
  const next = data.next_reminder
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
      {next && (
        <div className="mt-action">
          <button
            className="btn"
            type="button"
            disabled={!data.reminders.enabled || remind.isPending}
            title={data.reminders.enabled ? `Remind ${next.client.name} on Discord now` : 'Reminders are off'}
            onClick={() => remind.mutate(next.client.id)}
          >
            Send now
          </button>
          <SendResult mutation={remind} />
        </div>
      )}
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

  return (
    <section className="tile span-5">
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
          return <CalendarCell key={day} day={day} entry={byDay.get(day)} today={day === data.today} />
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
    </section>
  )
}

function CalendarCell({ day, entry, today }: { day: string; entry?: CalendarDay; today: boolean }) {
  const date = parseDate(day).getDate()
  const classes = ['mt-day', entry?.status, today && 'today'].filter(Boolean).join(' ')
  const label = entry
    ? `${formatDay(day)}: ${entry.entries.map((e) => `${e.client.name} ${formatNTD(e.amount)} ${e.status}`).join(', ')}`
    : undefined
  return (
    <span className={classes} title={label} aria-label={label} aria-current={today ? 'date' : undefined}>
      {date}
    </span>
  )
}

function RetainersTile({ data }: { data: Maintenance }) {
  const [editing, setEditing] = useState<Retainer>()
  const [opened, setOpened] = useState<Opened>()

  return (
    <section className="tile span-7">
      <div className="tile-head">
        <h2 className="mt-title">Retainers</h2>
        <span className="tile-label">This month</span>
      </div>
      {data.retainers.length === 0 && (
        <p className="empty-note">No retainers yet. Add one for a client's monthly maintenance.</p>
      )}
      <ul className="mt-rows">
        {data.retainers.map((retainer) => (
          <RetainerRow
            key={retainer.id}
            retainer={retainer}
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

type RowProps = { retainer: Retainer; today: string; onEdit: () => void; onMonth: (month: Month) => void }

function RetainerRow({ retainer, today, onEdit, onMonth }: RowProps) {
  const chip = monthChip(retainer, today)
  const month = retainer.this_month
  const actionable = retainer.collection === 'ask' && month !== null

  return (
    <li className={`mt-row${retainer.active ? '' : ' ended'}`}>
      <Avatar
        className={`mt-avatar ${tintClass(retainer.client.id)}`}
        aria-hidden="true"
        src={retainer.client.avatar_url}
        fallback={initials(retainer.client.name)}
      />
      <button className="mt-name" type="button" onClick={onEdit} aria-label={`Edit ${retainer.client.name} retainer`}>
        <b>{retainer.client.name}</b>
        <small>
          {retainer.project && `${retainer.project.name} · `}
          {scheduleText(retainer)}
        </small>
      </button>
      <span className="mt-amount">{formatNTD(retainer.amount)}</span>
      {retainer.collection === 'auto_transfer' ? (
        <span className="chip good mt-contact">Auto transfer</span>
      ) : retainer.ask_via ? (
        <span className="chip mt-contact" title={contactHandle(retainer.ask_via)}>
          {contactKinds[retainer.ask_via.kind].label} {contactHandle(retainer.ask_via)}
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

function RemindersTile({ data }: { data: Maintenance }) {
  const test = useSendTest()
  const { enabled, mention_user_id, mention, time, repeat_days, timezone } = data.reminders
  const me = mention?.display_name

  return (
    <section className="tile span-12 tint-blue">
      <div className="mt-hook">
        <div>
          <h2 className="tile-label">Reminders</h2>
          <p className="mt-hook-title">{enabled ? 'Discord webhook' : 'Discord webhook · not set up'}</p>
        </div>
        <ul className="mt-facts">
          <li>
            <b>{time}</b>
            on the due date, <Link to="/settings">{timezone}</Link>
          </li>
          <li>
            <b>Every {repeat_days} days</b>
            while unpaid
          </li>
          <li title={mention_user_id ? `Discord user ID ${mention_user_id}` : undefined}>
            {me ? (
              <b className="mt-me">
                <Avatar className="mt-me-avatar" src={mention?.avatar_url} fallback={initials(me)} />
                {me}
              </b>
            ) : (
              <b>{mention_user_id ? '@you' : 'No mention'}</b>
            )}
            {mention_user_id ? 'mentioned in each ping' : <Link to="/settings">set your Discord ID</Link>}
          </li>
        </ul>
        <div className="mt-hook-action">
          <button
            className="btn secondary"
            type="button"
            disabled={!enabled || test.isPending}
            onClick={() => test.mutate()}
          >
            Send test
          </button>
          <SendResult mutation={test} />
        </div>
      </div>
      {!enabled && (
        <p className="mt-hook-note">
          Reminders are off. Add a Discord webhook URL in <Link to="/settings">Settings</Link>.
        </p>
      )}
    </section>
  )
}
