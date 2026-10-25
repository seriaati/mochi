import { Link } from 'react-router'
import { contactHandle, contactUrl } from '../clients/contactKinds.ts'
import { KindLabel } from '../clients/KindLabel.tsx'
import { MessageLink } from '../clients/MessageLink.tsx'
import { useClients, type Client, type ContactKind } from '../clients/queries.ts'
import { Avatar } from '../components/Avatar.tsx'
import {
  daysBetween,
  formatDay,
  formatNTD,
  formatNumber,
  initials,
  parseDate,
  plural,
  timeAgo,
} from '../format.ts'
import { useRecordPayment } from '../maintenance/useRecordPayment.tsx'
import { useMaintenance, type Maintenance, type Month, type Retainer } from '../maintenance/queries.ts'
import { useProjects, type Project } from '../projects/queries.ts'
import { daysIn } from '../projects/schedule.ts'
import { Track } from '../projects/Track.tsx'
import { useSettings } from '../settings/queries.ts'
import { tintClass } from '../tint.ts'
import { useEarnings, type Earnings } from './queries.ts'
import './OverviewPage.css'

export function OverviewPage() {
  const maintenance = useMaintenance(null)
  const projects = useProjects()
  const clients = useClients()
  const settings = useSettings()
  const earnings = useEarnings()
  const error = [maintenance, projects, clients, settings, earnings].find((q) => q.error)?.error

  if (error) return <p className="status">Couldn't load the overview: {error.message}</p>
  if (!maintenance.data || !projects.data || !clients.data || !settings.data || !earnings.data) {
    return <p className="status">Loading overview…</p>
  }

  const data = maintenance.data
  const asks = upcomingAsks(data)
  const open = projects.data.filter((p) => p.status !== 'done')

  return (
    <div className="bento ov">
      <GreetingTile
        data={data}
        asks={asks}
        open={open}
        clients={clients.data}
        timezone={settings.data.timezone}
        userName={settings.data.user_name}
      />
      <NextTile data={data} next={asks.at(0)} />
      <OverdueTile data={data} />
      <EarnedTile earnings={earnings.data} today={data.today} />
      <RecurringTile data={data} />
      <ProjectsTile open={open} hasClients={clients.data.length > 0} />
      <ClientsTile clients={clients.data} />
    </div>
  )
}

type Ask = { retainer: Retainer; month: Month }

/** Unpaid "ask" months still to collect (coming up, or due within the grace days), soonest first. */
function upcomingAsks(data: Maintenance): Ask[] {
  return data.retainers
    .filter((retainer) => retainer.collection === 'ask')
    .flatMap((retainer) =>
      retainer.months
        .filter((m) => m.status === 'upcoming' || m.status === 'due')
        .map((month) => ({ retainer, month })),
    )
    .sort(
      (a, b) =>
        a.month.due_on.localeCompare(b.month.due_on) ||
        a.retainer.client.name.localeCompare(b.retainer.client.name),
    )
}

const WORDS = ['No', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine', 'Ten']

/** "Two" up to ten, then digits. */
function countWord(count: number): string {
  return WORDS[count] ?? String(count)
}

/** "today", "tomorrow", "Sunday" within the week, otherwise "25 Nov". */
function dayWord(iso: string, today: string): string {
  const days = daysBetween(today, iso)
  if (days === 0) return 'today'
  if (days === 1) return 'tomorrow'
  if (days > 1 && days < 7) return parseDate(iso).toLocaleDateString('en-US', { weekday: 'long' })
  return formatDay(iso)
}

/** "morning", "afternoon" or "evening" right now in the saved timezone. */
function partOfDay(timezone: string): string {
  const hour = Number(
    new Intl.DateTimeFormat('en-US', { hour: 'numeric', hourCycle: 'h23', timeZone: timezone }).format(
      new Date(),
    ),
  )
  if (hour >= 5 && hour < 12) return 'morning'
  if (hour >= 12 && hour < 18) return 'afternoon'
  return 'evening'
}

/** One line on what needs doing, most pressing first. */
function headline(data: Maintenance, asks: Ask[], open: Project[], clients: Client[]): string {
  if (clients.length === 0) return "Let's add your first client."
  const overdue = data.overdue.length
  const thisWeek = asks.filter((a) => daysBetween(data.today, a.month.due_on) < 7).length
  if (overdue && !thisWeek) return `${countWord(overdue)} ${overdue === 1 ? 'payment is' : 'payments are'} overdue.`
  const payments = overdue + thisWeek
  if (payments) return `${countWord(payments)} ${payments === 1 ? 'payment needs' : 'payments need'} you this week.`
  const deadline = open
    .filter((p) => !p.delivered_on && p.due_on && daysBetween(data.today, p.due_on) >= 0)
    .find((p) => daysBetween(data.today, p.due_on!) < 7)
  if (deadline) return `${deadline.name} is due ${dayWord(deadline.due_on!, data.today)}.`
  return 'Nothing needs you today.'
}

type GreetingProps = {
  data: Maintenance
  asks: Ask[]
  open: Project[]
  clients: Client[]
  timezone: string
  userName: string | null
}

function GreetingTile({ data, asks, open, clients, timezone, userName }: GreetingProps) {
  const today = parseDate(data.today)
  const date = `${today.toLocaleDateString('en-US', { weekday: 'long' })}, ${today.getDate()} ${today.toLocaleDateString('en-US', { month: 'long' })}`
  const name = userName ?? data.reminders.mention?.display_name
  const greeting = `Good ${partOfDay(timezone)}${name ? `, ${name}` : ''}.`

  const next = asks.at(0)
  const dueTogether = next ? asks.filter((a) => a.month.due_on === next.month.due_on).length : 0
  const overdue = data.overdue.length

  return (
    <section className="tile span-5 ov-greeting">
      <p className="tile-label">{date}</p>
      <h1 className="ov-headline">
        {greeting} {headline(data, asks, open, clients)}
      </h1>
      <div className="ov-chips">
        {clients.length === 0 ? (
          <Link className="btn" to="/clients">
            Add your first client
          </Link>
        ) : (
          <>
            {overdue > 0 && (
              <Link className="chip warn" to="/maintenance">
                {overdue} overdue
              </Link>
            )}
            {next && (
              <Link className="chip" to="/maintenance">
                {dueTogether} due {dayWord(next.month.due_on, data.today)}
              </Link>
            )}
            {open.length > 0 && (
              <Link className="chip" to="/projects">
                {plural(open.length, 'active project')}
              </Link>
            )}
            {!overdue && !next && !open.length && <span className="chip good">All caught up</span>}
          </>
        )}
      </div>
    </section>
  )
}

function NextTile({ data, next }: { data: Maintenance; next?: Ask }) {
  const [dialog, record] = useRecordPayment()

  if (!next) {
    const hasAsks = data.retainers.some((r) => r.collection === 'ask' && r.active)
    return (
      <section className="tile span-4 ink ov-summary">
        <h2 className="tile-label">Next to collect</h2>
        <p className="ov-who">Nothing to ask for</p>
        <p className="ov-meta">
          {hasAsks ? 'No fee you ask for is coming up.' : 'Monthly fees you ask clients for show up here.'}
        </p>
        <div className="ov-action">
          <Link className="btn" to="/maintenance">
            {hasAsks ? 'Open retainers' : 'Add a retainer'}
          </Link>
        </div>
        {dialog}
      </section>
    )
  }

  const { retainer, month } = next
  const contact = retainer.ask_via
  const handle = contact && (
    <>
      <KindLabel kind={contact.kind} /> {contactHandle(contact)}
    </>
  )
  const url = contact && contactUrl(contact)

  return (
    <section className="tile span-4 ink ov-summary">
      <h2 className="tile-label">Next to collect</h2>
      <p className="ov-who">
        <Link to={`/clients/${retainer.client.id}`}>{retainer.client.name}</Link>
      </p>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(month.amount)}
      </p>
      <p className="ov-meta">
        Due {formatDay(month.due_on, { weekday: true })} ·{' '}
        {url ? (
          <a href={url} target={url.startsWith('https:') ? '_blank' : undefined} rel="noreferrer">
            {handle}
          </a>
        ) : (
          (handle ?? 'no contact set')
        )}
      </p>
      <div className="ov-action">
        <button className="btn" type="button" onClick={() => record(retainer, month.period)}>
          Record payment
        </button>
      </div>
      {dialog}
    </section>
  )
}

function OverdueTile({ data }: { data: Maintenance }) {
  const [dialog, record] = useRecordPayment()
  const [worst] = data.overdue
  const retainer = data.retainers.find((r) => r.id === worst?.retainer_id)

  if (!worst || !retainer) {
    return (
      <section className="tile span-3 tint-sage ov-summary">
        <h2 className="tile-label">Overdue</h2>
        <p className="ov-who">All paid up</p>
        <p className="ov-meta">Nothing is overdue.</p>
        {dialog}
      </section>
    )
  }

  // The client overdue the longest, with all they owe past the grace days.
  const theirs = data.overdue.filter((o) => o.client.id === worst.client.id)
  const others = new Set(data.overdue.map((o) => o.client.id)).size - 1
  const reminded = worst.last_reminded_on
  return (
    <section className="tile span-3 tint-peach ov-summary ov-overdue">
      <h2 className="tile-label">Overdue · {plural(worst.days, 'day')}</h2>
      <p className="ov-who">
        <Link to={`/clients/${worst.client.id}`}>{worst.client.name}</Link>
      </p>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(theirs.reduce((sum, o) => sum + o.amount, 0))}
      </p>
      <p className="ov-meta">
        {reminded ? `Reminded ${formatDay(reminded)}` : 'Not reminded yet'}
        {others > 0 && ` · ${plural(others, 'more client')} overdue`}
      </p>
      <div className="ov-action">
        <button className="btn" type="button" onClick={() => record(retainer, worst.period)}>
          Record payment
        </button>
        <MessageLink contact={retainer.ask_via} />
      </div>
      {dialog}
    </section>
  )
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function EarnedTile({ earnings, today }: { earnings: Earnings; today: string }) {
  const { year, months, total, change_percent: change } = earnings
  const thisYear = Number(today.slice(0, 4))
  // The month in progress; earlier ones are done and later ones still to come.
  const current = year === thisYear ? Number(today.slice(5, 7)) - 1 : year < thisYear ? 12 : -1
  const max = Math.max(...months, 1)

  return (
    <section className="tile span-7">
      <div className="tile-head ov-earned-head">
        <div>
          <h2 className="tile-label">Earned in {year}</h2>
          <p className="big-number">
            <small>NT$</small>
            {formatNumber(total)}
          </p>
          {total === 0 && <p className="ov-sub">No payments received yet this year.</p>}
        </div>
        {change !== null && (
          <span className={`chip${change >= 0 ? ' good' : ''}`}>
            {change >= 0 ? '+' : '−'}
            {Math.abs(change)}% vs {year - 1}
          </span>
        )}
      </div>
      <div className="ov-chart" role="list" aria-label={`Earned per month in ${year}`}>
        {months.map((amount, i) => {
          const future = i > current
          const label = `${MONTHS[i]}: ${future ? 'still to come' : formatNTD(amount)}`
          return (
            <i
              key={MONTHS[i]}
              role="listitem"
              aria-label={label}
              title={label}
              className={future ? 'future' : i === current ? 'now' : undefined}
              style={{ height: future ? '20%' : `${Math.max((amount / max) * 100, 3)}%` }}
            />
          )
        })}
      </div>
      <div className="ov-months" aria-hidden="true">
        {MONTHS.map((m, i) => (
          <span key={m} className={i === current ? 'now' : undefined}>
            {m}
          </span>
        ))}
      </div>
    </section>
  )
}

const RING_RADIUS = 44
const RING_LENGTH = 2 * Math.PI * RING_RADIUS

function RecurringTile({ data }: { data: Maintenance }) {
  const total = data.monthly_total
  const auto = data.automatic.amount
  const share = total ? auto / total : 0
  const percent = Math.round(share * 100)

  return (
    <section className="tile span-5 tint-sage">
      <h2 className="tile-label">Recurring maintenance</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(total)}
        <small>/mo</small>
      </p>
      <p className="ov-sub">{plural(data.active_count, 'retainer')}</p>
      <div className="ov-ring">
        <svg
          width="112"
          height="112"
          viewBox="0 0 112 112"
          role="img"
          aria-label={total ? `${percent}% of recurring income is paid automatically` : 'No recurring income yet'}
        >
          <circle className="ov-ring-track" cx="56" cy="56" r={RING_RADIUS} />
          {share > 0 && (
            <circle
              className="ov-ring-auto"
              cx="56"
              cy="56"
              r={RING_RADIUS}
              strokeDasharray={`${share * RING_LENGTH} ${RING_LENGTH}`}
              transform="rotate(-90 56 56)"
            />
          )}
          <text x="56" y="61" textAnchor="middle">
            {total ? `${percent}%` : '–'}
          </text>
        </svg>
        {total === 0 ? (
          <p className="ov-empty">
            No monthly fees yet. <Link to="/maintenance">Add a retainer</Link> and see how much arrives by
            itself.
          </p>
        ) : (
          <ul className="ov-legend">
            <li>
              <i className="auto" />
              Auto bank transfer<b>{formatNTD(auto)}</b>
            </li>
            <li>
              <i />
              You ask manually<b>{formatNTD(total - auto)}</b>
            </li>
          </ul>
        )}
      </div>
    </section>
  )
}

const SHOWN_PROJECTS = 4

function ProjectsTile({ open, hasClients }: { open: Project[]; hasClients: boolean }) {
  return (
    <section className="tile span-8">
      <div className="tile-head">
        <h2 className="tile-label">Projects in progress</h2>
        <Link className="ov-link" to="/projects">
          {open.length > SHOWN_PROJECTS ? `See all ${open.length}` : 'See all'}
        </Link>
      </div>
      {open.length === 0 ? (
        <p className="ov-empty">
          {hasClients ? 'Nothing in progress. ' : 'Projects show up here once you have a client. '}
          <Link to={hasClients ? '/projects' : '/clients'}>{hasClients ? 'Start a project' : 'Add a client'}</Link>
        </p>
      ) : (
        <ul className="ov-projects">
          {open.slice(0, SHOWN_PROJECTS).map((project) => (
            <li key={project.id}>
              <ProjectRow project={project} />
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function ProjectRow({ project }: { project: Project }) {
  const additions = project.additions.length
  let dates = `Started ${formatDay(project.started_on)} · ${plural(daysIn(project), 'day')} in`
  if (project.delivered_on) dates = `${formatDay(project.started_on)} – delivered ${formatDay(project.delivered_on)}`
  else if (project.due_on) dates = `${formatDay(project.started_on)} – ${formatDay(project.due_on)}`

  return (
    <Link className="ov-project" to={`/projects/${project.id}`}>
      <Avatar
        className={`ov-project-avatar ${tintClass(project.client.id)}`}
        aria-hidden="true"
        src={project.client.avatar_url}
        fallback={initials(project.client.name)}
      />
      <div className="ov-project-name">
        <b>{project.name}</b>
        <small>
          {project.client.name}
          {additions > 0 && ` · ${plural(additions, 'addition')}`}
          {project.status === 'final_payment_due' && ' · final payment due'}
        </small>
      </div>
      <div>
        <Track project={project} />
        <p className="ov-project-dates">{dates}</p>
      </div>
      <p className="ov-project-total">
        {formatNTD(project.total)}
        {project.additions_total > 0 && <small>+{formatNTD(project.additions_total)}</small>}
      </p>
    </Link>
  )
}

const STACK_SIZE = 6
const CHANNELS: ContactKind[] = ['discord', 'line', 'email', 'other']

function ClientsTile({ clients }: { clients: Client[] }) {
  const contacts = clients.flatMap((c) => c.contacts)
  const profiles = contacts.flatMap((c) => (c.discord_profile ? [c.discord_profile] : []))
  const syncing = profiles.some((p) => p.status !== 'off')
  const lastSync = profiles.map((p) => p.synced_at).filter((at) => at !== null).sort().at(-1)
  const reach = (kind: ContactKind) => clients.filter((c) => c.contacts.some((m) => m.kind === kind)).length

  return (
    <section className="tile span-4 tint-lavender">
      <div className="tile-head">
        <h2 className="tile-label">Clients</h2>
        <Link className="ov-link" to="/clients">
          Manage
        </Link>
      </div>
      <p className="big-number">{clients.length}</p>
      {clients.length === 0 ? (
        <>
          <p className="ov-empty">Everyone you work with, and how to reach them.</p>
          <div className="ov-action">
            <Link className="btn secondary" to="/clients">
              Add a client
            </Link>
          </div>
        </>
      ) : (
        <>
          <ul className="ov-stack">
            {clients.slice(0, STACK_SIZE).map((client) => (
              <li key={client.id} title={client.name}>
                <Link to={`/clients/${client.id}`} aria-label={client.name}>
                  <Avatar
                    className={`ov-stack-avatar ${tintClass(client.id)}`}
                    src={client.avatar_url}
                    fallback={initials(client.name)}
                  />
                </Link>
              </li>
            ))}
            {clients.length > STACK_SIZE && (
              <li>
                <span className="ov-stack-avatar ov-stack-more">+{clients.length - STACK_SIZE}</span>
              </li>
            )}
          </ul>
          <ul className="ov-channels">
            {CHANNELS.filter((kind) => kind !== 'other' || reach(kind) > 0).map((kind) => (
              <li key={kind}>
                <KindLabel kind={kind} />
                <b>
                  {reach(kind)}
                  {kind === 'discord' && syncing && lastSync && ` · synced ${timeAgo(lastSync)}`}
                </b>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  )
}
