import { useState, type ReactNode } from 'react'
import { Link } from 'react-router'
import { useClients, type Client } from '../clients/queries.ts'
import { Avatar } from '../components/Avatar.tsx'
import { Segmented } from '../components/Segmented.tsx'
import { Select } from '../components/Select.tsx'
import { Skeleton } from '../components/Skeleton.tsx'
import { daysBetween, formatDay, formatMonth, formatNTD, formatNumber, initials, plural } from '../format.ts'
import { useMaintenance, type Overdue, type Retainer } from '../maintenance/queries.ts'
import { useProjects, type Project } from '../projects/queries.ts'
import { tintClass } from '../tint.ts'
import { ColumnChart, Legend, LineChart, NoData } from './charts.tsx'
import { useIncome, type IncomeEntry, type Source } from './queries.ts'
import {
  SOURCES,
  bucketsFor,
  byMonth,
  mean,
  median,
  percent,
  rangeFor,
  sourceColor,
  sourceLabels,
  splitOf,
  sum,
  within,
  yearBefore,
  type Bucket,
  type Period,
  type Range,
  type Split,
} from './slice.ts'
import './StatsPage.css'

const kinds = {
  all: { label: 'All income', sources: SOURCES },
  projects: { label: 'Projects', sources: ['project', 'addition'] as Source[] },
  retainers: { label: 'Retainers', sources: ['retainer'] as Source[] },
}

type Kind = keyof typeof kinds

export function StatsPage() {
  const income = useIncome()
  const projects = useProjects()
  const maintenance = useMaintenance(null)
  const clients = useClients()
  const [period, setPeriod] = useState<Period>('last12')
  const [client, setClient] = useState('all')
  const [kind, setKind] = useState<Kind>('all')

  const error = [income, projects, maintenance, clients].find((q) => q.error)?.error
  const head = (
    <div className="page-head">
      <div>
        <h1 className="page-title">Stats</h1>
        <p className="page-sub">How your freelancing is going, in numbers</p>
      </div>
    </div>
  )

  if (error) return <>{head}<p className="status">Couldn't load your stats: {error.message}</p></>
  if (!income.data || !projects.data || !maintenance.data || !clients.data) {
    return (
      <>
        {head}
        <Skeleton
          label="Loading stats"
          tiles={[
            { span: 'span-6', height: 200 },
            { span: 'span-3', height: 200 },
            { span: 'span-3', height: 200 },
            { span: 'span-12', height: 340 },
            { span: 'span-7', height: 320 },
            { span: 'span-5', height: 320 },
          ]}
        />
      </>
    )
  }

  const { today } = income.data
  const allProjects = projects.data
  if (income.data.entries.length === 0 && allProjects.length === 0 && maintenance.data.retainers.length === 0) {
    return (
      <>
        {head}
        <div className="bento">
          <section className="tile span-12">
            <h2 className="tile-label">Nothing to count yet</h2>
            <p className="empty-note">
              Charts, comparisons and records show up here once money comes in.{' '}
              <Link className="st-link" to={clients.data.length ? '/projects' : '/clients'}>
                {clients.data.length ? 'Start a project' : 'Add your first client'}
              </Link>
            </p>
          </section>
        </div>
      </>
    )
  }

  const clientId = client === 'all' ? null : Number(client)
  const sources = kinds[kind].sources
  const ofClient = <T extends { client: { id: number } }>(record: T) => clientId === null || record.client.id === clientId
  const entries = income.data.entries.filter((e) => ofClient(e) && sources.includes(e.source))
  const theirProjects = allProjects.filter(ofClient)
  const retainers = maintenance.data.retainers.filter(ofClient)
  const overdue = maintenance.data.overdue.filter(ofClient)

  // Years with anything in them, whoever it's from, so the list stays put as the filters change.
  const years = new Set([today.slice(0, 4)])
  for (const e of income.data.entries) years.add(e.paid_on.slice(0, 4))
  for (const p of allProjects) if (p.started_on <= today) years.add(p.started_on.slice(0, 4))
  const earliest = [today, entries[0]?.paid_on, ...theirProjects.map((p) => p.started_on)]
    .filter((d): d is string => !!d)
    .sort()[0]
  const range = rangeFor(period, today, earliest)
  const current = entries.filter((e) => within(e, range.first, range.last))
  const before = range.previous && entries.filter((e) => within(e, range.previous!.first, range.previous!.last))
  // Nothing then is nothing to compare with.
  const previous = before?.length ? before : null
  const months = byMonth(current)
  const monthTotals = range.months.map((m) => sum(sources.map((s) => months.get(m)?.[s] ?? 0)))

  const showProjects = kind !== 'retainers'
  const showRetainers = kind !== 'projects'
  const sortedClients = [...clients.data].sort((a, b) => a.name.localeCompare(b.name))

  return (
    <>
      {head}
      <div className="st-toolbar">
        <div className="st-select st-period">
          <Select
            aria-label="Period"
            value={period}
            onChange={setPeriod}
            options={[
              { value: 'last12', label: 'Last 12 months' },
              ...[...years].sort().reverse().map((year) => ({ value: year as Period, label: year })),
              { value: 'all', label: 'All time' },
            ]}
          />
        </div>
        <div className="st-select st-client">
          <Select
            aria-label="Client"
            value={client}
            onChange={setClient}
            options={[
              { value: 'all', label: 'All clients' },
              ...sortedClients.map((c) => ({ value: String(c.id), label: c.name })),
            ]}
          />
        </div>
        <Segmented role="group" aria-label="Income from">
          {(Object.keys(kinds) as Kind[]).map((key) => (
            <button key={key} type="button" aria-pressed={kind === key} onClick={() => setKind(key)}>
              {kinds[key].label}
            </button>
          ))}
        </Segmented>
      </div>

      <div className="bento st">
        <EarnedTile current={current} previous={previous} range={range} />
        <AverageTile totals={monthTotals} />
        <BestTile months={range.months} totals={monthTotals} />
        <IncomeTile range={range} months={months} sources={sources} />
        <RunningTile range={range} current={current} previous={previous} />
        <ShareTile entries={current} range={range} client={clientId} clients={clients.data} />
        {showProjects && (
          <ProjectsTile projects={theirProjects.filter((p) => p.started_on >= range.first && p.started_on <= range.last)} range={range} wide={!showRetainers} />
        )}
        {showRetainers && (
          <RetainersTile retainers={retainers} overdue={overdue} current={current} range={range} wide={!showProjects} />
        )}
        <YearsTile entries={entries} projects={theirProjects} sources={sources} today={today} />
        <PaymentsTile entries={current} range={range} />
      </div>
    </>
  )
}

/** "+12%" or "−8%", from a whole percent. */
const signed = (change: number) => `${change >= 0 ? '+' : '−'}${Math.abs(change)}%`

/** Whole percent change from `before` to `after`, or null without a before. */
const change = (after: number, before: number) => (before ? Math.round(((after - before) * 100) / before) : null)

type EarnedProps = { current: IncomeEntry[]; previous: IncomeEntry[] | null; range: Range }

function EarnedTile({ current, previous, range }: EarnedProps) {
  const earned = sum(current.map((e) => e.amount))
  const before = previous && sum(previous.map((e) => e.amount))
  const delta = before === null ? null : change(earned, before)
  const payers = new Set(current.map((e) => e.client.id)).size

  return (
    <section className="tile span-6 ink">
      <div className="tile-head st-earned-head">
        <h2 className="tile-label">Earned {range.phrase}</h2>
        {delta !== null && (
          <span className={`st-delta${delta >= 0 ? ' up' : ''}`}>
            {signed(delta)} vs {range.previous!.label.toLowerCase()}
          </span>
        )}
      </div>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(earned)}
      </p>
      <p className="st-meta">
        {current.length ? `${plural(current.length, 'payment')} from ${plural(payers, 'client')}` : 'Nothing received yet.'}
      </p>
      {before !== null && (
        <p className="st-meta st-earned-before">
          {formatNTD(before)} {range.previous!.phrase}
        </p>
      )}
    </section>
  )
}

function AverageTile({ totals }: { totals: number[] }) {
  return (
    <section className="tile span-3 tint-sage">
      <h2 className="tile-label">Monthly average</h2>
      <p className="big-number st-figure">
        <small>NT$</small>
        {formatNumber(Math.round(mean(totals)))}
      </p>
      <p className="st-meta">Median {formatNTD(Math.round(median(totals)))}</p>
      <p className="st-meta">Over {plural(totals.length, 'month')}</p>
    </section>
  )
}

function BestTile({ months, totals }: { months: string[]; totals: number[] }) {
  const best = totals.indexOf(Math.max(...totals))
  const quietest = totals.indexOf(Math.min(...totals))
  return (
    <section className="tile span-3 tint-yellow">
      <h2 className="tile-label">Best month</h2>
      {totals[best] > 0 ? (
        <>
          <p className="big-number st-figure">
            <small>NT$</small>
            {formatNumber(totals[best])}
          </p>
          <p className="st-meta">{formatMonth(`${months[best]}-01`)}</p>
          {months.length > 1 && (
            <p className="st-meta">
              Quietest: {formatMonth(`${months[quietest]}-01`)}, {formatNTD(totals[quietest])}
            </p>
          )}
        </>
      ) : (
        <p className="empty-note">Your best month shows here once money comes in.</p>
      )}
    </section>
  )
}

type IncomeProps = { range: Range; months: Map<string, Split>; sources: Source[] }

function IncomeTile({ range, months, sources }: IncomeProps) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const buckets = bucketsFor(range.months)
  const splits = buckets.map((b) => splitOf(b, months))
  const totals = splits.map((split) => sum(sources.map((s) => split[s])))
  const unit = buckets[0].months.length > 1 ? 'year' : 'month'
  const empty = totals.every((t) => t === 0)

  return (
    <section className="tile span-12">
      <div className="tile-head st-head">
        <h2 className="tile-label">Received by {unit}</h2>
        {!empty && (
          <Segmented role="group" aria-label="Show as" className="st-view">
            <button type="button" aria-pressed={view === 'chart'} onClick={() => setView('chart')}>
              Chart
            </button>
            <button type="button" aria-pressed={view === 'table'} onClick={() => setView('table')}>
              Table
            </button>
          </Segmented>
        )}
      </div>
      {empty ? (
        <NoData>Nothing received {range.phrase}. Payments you record on projects and retainers show up here.</NoData>
      ) : view === 'chart' ? (
        <>
          {sources.length > 1 && (
            <Legend items={sources.map((s) => ({ key: s, label: sourceLabels[s], color: sourceColor(s) }))} />
          )}
          <ColumnChart buckets={buckets} splits={splits} sources={sources} label={`Received by ${unit} ${range.phrase}`} />
        </>
      ) : (
        <IncomeTable buckets={buckets} splits={splits} totals={totals} sources={sources} unit={unit} />
      )}
    </section>
  )
}

type IncomeTableProps = { buckets: Bucket[]; splits: Split[]; totals: number[]; sources: Source[]; unit: string }

function IncomeTable({ buckets, splits, totals, sources, unit }: IncomeTableProps) {
  const running = totals.map((_, i) => sum(totals.slice(0, i + 1)))
  return (
    <div className="st-scroll">
      <table className="st-table">
        <thead>
          <tr>
            <th>{unit === 'year' ? 'Year' : 'Month'}</th>
            {sources.length > 1 && sources.map((s) => <th key={s} className="num">{sourceLabels[s]}</th>)}
            <th className="num">Total</th>
            <th className="num">Running total</th>
          </tr>
        </thead>
        <tbody>
          {buckets.map((bucket, i) => (
            <tr key={bucket.title}>
              <td>{bucket.title}</td>
              {sources.length > 1 && sources.map((s) => <td key={s} className="num">{formatNTD(splits[i][s])}</td>)}
              <td className="num strong">{formatNTD(totals[i])}</td>
              <td className="num">{formatNTD(running[i])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Running totals at the end of each bucket, for entries whose month maps into `range`. */
function runningTotals(buckets: Bucket[], entries: IncomeEntry[], shift = 0): number[] {
  const months = new Map<string, number>()
  for (const e of entries) {
    const [year, month] = e.paid_on.split('-').map(Number)
    const key = `${year + shift}-${String(month).padStart(2, '0')}`
    months.set(key, (months.get(key) ?? 0) + e.amount)
  }
  let running = 0
  return buckets.map((bucket) => (running += sum(bucket.months.map((m) => months.get(m) ?? 0))))
}

type RunningProps = { range: Range; current: IncomeEntry[]; previous: IncomeEntry[] | null }

function RunningTile({ range, current, previous }: RunningProps) {
  const buckets = bucketsFor(range.months)
  const now = runningTotals(buckets, current)
  const before = previous && runningTotals(buckets, previous, 1)
  const lines = [
    { key: 'now', label: range.label, color: 'var(--ink)', values: now },
    ...(before ? [{ key: 'before', label: range.previous!.label, color: 'var(--dim)', values: before }] : []),
  ]
  const empty = now.at(-1) === 0 && !before?.at(-1)

  return (
    <section className="tile span-7">
      <h2 className="tile-label">Running total{before ? ` vs ${range.previous!.label.toLowerCase()}` : ''}</h2>
      {empty ? (
        <NoData>Nothing received {range.phrase} to add up.</NoData>
      ) : (
        <>
          {before && <Legend items={lines.map((l) => ({ ...l, line: true }))} />}
          <LineChart
            buckets={buckets}
            lines={lines}
            label={
              `Running total ${range.phrase}: ${formatNTD(now.at(-1)!)}` +
              (before ? `, against ${formatNTD(before.at(-1)!)} ${range.previous!.phrase}` : '')
            }
            extra={
              before
                ? (i) => {
                    const gap = now[i] - before[i]
                    return [{ key: 'gap', value: `${gap >= 0 ? '+' : '−'}${formatNTD(Math.abs(gap))}`, label: gap >= 0 ? 'ahead' : 'behind' }]
                  }
                : undefined
            }
          />
        </>
      )}
    </section>
  )
}

const SHOWN_SHARES = 6

type ShareProps = { entries: IncomeEntry[]; range: Range; client: number | null; clients: Client[] }

/** Who the money came from, or with one client picked, what for. */
function ShareTile({ entries, range, client, clients }: ShareProps) {
  type Row = { key: string; name: string; to?: string; amount: number; avatar?: Client | { id: number; name: string } }
  const rows = new Map<string, Row>()
  for (const e of entries) {
    const row: Row =
      client === null
        ? { key: `c${e.client.id}`, name: e.client.name, to: `/clients/${e.client.id}`, amount: 0, avatar: clients.find((c) => c.id === e.client.id) ?? e.client }
        : e.project
          ? { key: `p${e.project.id}`, name: e.project.name, to: `/projects/${e.project.id}`, amount: 0 }
          : { key: 'none', name: 'Retainers without a project', amount: 0 }
    const found = rows.get(row.key) ?? row
    found.amount += e.amount
    rows.set(row.key, found)
  }
  const ranked = [...rows.values()].sort((a, b) => b.amount - a.amount)
  const whole = sum(ranked.map((r) => r.amount))
  const shown = ranked.slice(0, SHOWN_SHARES)
  const rest = ranked.slice(SHOWN_SHARES)
  const top = shown[0]?.amount ?? 1

  return (
    <section className="tile span-5 tint-lavender">
      <h2 className="tile-label">{client === null ? 'By client' : 'By project'}</h2>
      {ranked.length === 0 ? (
        <NoData>Nothing received {range.phrase}.</NoData>
      ) : (
        <ol className="st-shares">
          {shown.map((row) => (
            <li key={row.key}>
              <div className="st-share-name">
                {row.avatar && (
                  <Avatar
                    className={`st-share-avatar ${tintClass(row.avatar.id)}`}
                    aria-hidden="true"
                    src={'avatar_url' in row.avatar ? row.avatar.avatar_url : null}
                    fallback={initials(row.name)}
                  />
                )}
                {row.to ? <Link to={row.to}>{row.name}</Link> : <span>{row.name}</span>}
                <b>{formatNTD(row.amount)}</b>
                <small>{percent(row.amount, whole)}%</small>
              </div>
              <span className="track st-share-bar" aria-hidden="true">
                <i style={{ width: `${(row.amount / top) * 100}%` }} />
              </span>
            </li>
          ))}
          {rest.length > 0 && (
            <li className="st-share-rest">
              {plural(rest.length, client === null ? 'more client' : 'more project')} ·{' '}
              {formatNTD(sum(rest.map((r) => r.amount)))}
            </li>
          )}
        </ol>
      )}
    </section>
  )
}

type Fact = { label: string; value: ReactNode; note?: ReactNode }

function Facts({ facts }: { facts: Fact[] }) {
  return (
    <dl className="st-facts">
      {facts.map((fact) => (
        <div key={fact.label}>
          <dt>{fact.label}</dt>
          <dd>
            {fact.value}
            {fact.note && <small>{fact.note}</small>}
          </dd>
        </div>
      ))}
    </dl>
  )
}

const days = (n: number) => plural(Math.round(n), 'day')

function ProjectsTile({ projects, range, wide }: { projects: Project[]; range: Range; wide: boolean }) {
  const delivered = projects.filter((p) => p.delivered_on)
  const lengths = delivered.map((p) => daysBetween(p.started_on, p.delivered_on!))
  const dated = delivered.filter((p) => p.due_on)
  const onTime = dated.filter((p) => p.delivered_on! <= p.due_on!).length
  const additions = projects.flatMap((p) => p.additions)
  const withAdditions = projects.filter((p) => p.additions.length).length
  const biggest = [...projects].sort((a, b) => b.total - a.total)[0]
  const values = projects.map((p) => p.total)

  return (
    <section className={`tile ${wide ? 'span-12' : 'span-6'}`}>
      <h2 className="tile-label">Projects started {range.phrase}</h2>
      {projects.length === 0 ? (
        <NoData>
          No projects started {range.phrase}. <Link className="st-link" to="/projects">Open projects</Link>
        </NoData>
      ) : (
        <Facts
          facts={[
            { label: 'Started', value: projects.length, note: `${delivered.length} delivered` },
            { label: 'Average value', value: formatNTD(Math.round(mean(values))), note: `Median ${formatNTD(Math.round(median(values)))}` },
            {
              label: 'Biggest',
              value: formatNTD(biggest.total),
              note: <Link to={`/projects/${biggest.id}`}>{biggest.name}</Link>,
            },
            {
              label: 'Start to delivery',
              value: lengths.length ? days(mean(lengths)) : '–',
              note: lengths.length ? `Median ${days(median(lengths))}` : 'Nothing delivered yet',
            },
            {
              label: 'Delivered on time',
              value: dated.length ? `${percent(onTime, dated.length)}%` : '–',
              note: dated.length ? `${onTime} of ${plural(dated.length, 'project')} with a due date` : 'None had a due date',
            },
            {
              label: 'Additions',
              value: formatNTD(sum(additions.map((a) => a.price))),
              note: `${plural(additions.length, 'addition')}, on ${percent(withAdditions, projects.length)}% of projects`,
            },
            { label: 'Still to be paid', value: formatNTD(sum(projects.map((p) => p.total_outstanding))) },
            { label: 'Received so far', value: formatNTD(sum(projects.map((p) => p.total_paid))), note: `of ${formatNTD(sum(values))}` },
          ]}
        />
      )}
    </section>
  )
}

type RetainersProps = { retainers: Retainer[]; overdue: Overdue[]; current: IncomeEntry[]; range: Range; wide: boolean }

function RetainersTile({ retainers, overdue, current, range, wide }: RetainersProps) {
  const active = retainers.filter((r) => r.active)
  const monthly = sum(active.map((r) => r.amount))
  const auto = sum(active.filter((r) => r.collection === 'auto_transfer').map((r) => r.amount))
  const fees = current.filter((e) => e.source === 'retainer')
  const asked = fees.filter((e) => e.collection === 'ask')
  const onTime = asked.filter((e) => !e.late).length
  const started = retainers.filter((r) => r.started_on >= range.first && r.started_on <= range.last).length
  const ended = retainers.filter((r) => r.ended_on && r.ended_on >= range.first && r.ended_on <= range.last).length

  return (
    <section className={`tile ${wide ? 'span-12' : 'span-6'}`}>
      <h2 className="tile-label">Retainers</h2>
      {retainers.length === 0 ? (
        <NoData>
          No retainers yet. <Link className="st-link" to="/maintenance">Add a retainer</Link>
        </NoData>
      ) : (
        <Facts
          facts={[
            { label: 'Monthly now', value: formatNTD(monthly), note: plural(active.length, 'active retainer') },
            { label: `Received ${range.phrase}`, value: formatNTD(sum(fees.map((e) => e.amount))), note: plural(fees.length, 'payment') },
            {
              label: 'Paid on time',
              value: asked.length ? `${percent(onTime, asked.length)}%` : '–',
              note: asked.length ? `${onTime} of ${plural(asked.length, 'fee')} you asked for` : 'No fees asked for',
            },
            {
              label: 'Paid after the due date',
              value: asked.length ? days(mean(asked.map((e) => e.days_late ?? 0))) : '–',
              note: 'On average',
            },
            { label: 'Paid automatically', value: monthly ? `${percent(auto, monthly)}%` : '–', note: monthly ? `${formatNTD(auto)} a month` : undefined },
            {
              label: 'Overdue now',
              value: formatNTD(sum(overdue.map((o) => o.amount))),
              note: overdue.length ? <Link to="/maintenance#overdue">{plural(overdue.length, 'month')}</Link> : 'All paid up',
            },
            { label: `Started ${range.phrase}`, value: started },
            { label: `Ended ${range.phrase}`, value: ended },
          ]}
        />
      )}
    </section>
  )
}

type YearsProps = { entries: IncomeEntry[]; projects: Project[]; sources: Source[]; today: string }

/** Every year side by side; the current one so far, compared with the year before by this date. */
function YearsTile({ entries, projects, sources, today }: YearsProps) {
  const thisYear = Number(today.slice(0, 4))
  const first = Math.min(thisYear, ...entries.map((e) => Number(e.paid_on.slice(0, 4))), ...projects.map((p) => Number(p.started_on.slice(0, 4))))
  const yearOf = (year: number) => {
    const last = year === thisYear ? today : `${year}-12-31`
    const range = rangeFor(String(year) as Period, today, today)
    const months = byMonth(entries.filter((e) => within(e, range.first, last)))
    const totals = range.months.map((m) => sum(sources.map((s) => months.get(m)?.[s] ?? 0)))
    const earned = sum(totals)
    const before = sum(entries.filter((e) => within(e, `${year - 1}-01-01`, yearBefore(last))).map((e) => e.amount))
    const best = totals.indexOf(Math.max(...totals))
    return {
      year,
      earned,
      delta: year > first ? change(earned, before) : null,
      average: Math.round(mean(totals)),
      best: earned ? `${formatMonth(`${range.months[best]}-01`).slice(0, 3)}, ${formatNTD(totals[best])}` : '–',
      started: projects.filter((p) => p.started_on.startsWith(String(year))).length,
    }
  }
  const rows = Array.from({ length: thisYear - first + 1 }, (_, i) => yearOf(thisYear - i))
  const withProjects = sources.includes('project')

  return (
    <section className="tile span-12">
      <h2 className="tile-label">Year by year</h2>
      <div className="st-scroll">
        <table className="st-table">
          <thead>
            <tr>
              <th>Year</th>
              <th className="num">Earned</th>
              <th className="num">Change</th>
              <th className="num">Monthly average</th>
              <th>Best month</th>
              {withProjects && <th className="num">Projects started</th>}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.year}>
                <td className="nowrap">
                  {row.year}
                  {row.year === thisYear && <small> so far</small>}
                </td>
                <td className="num strong">{formatNTD(row.earned)}</td>
                <td className="num">
                  {row.delta === null ? '–' : <span className={row.delta >= 0 ? 'st-up' : undefined}>{signed(row.delta)}</span>}
                </td>
                <td className="num">{formatNTD(row.average)}</td>
                <td className="nowrap">{row.best}</td>
                {withProjects && <td className="num">{row.started}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

const orders = {
  newest: { label: 'Newest', compare: (a: IncomeEntry, b: IncomeEntry) => b.paid_on.localeCompare(a.paid_on) },
  biggest: { label: 'Biggest', compare: (a: IncomeEntry, b: IncomeEntry) => b.amount - a.amount || b.paid_on.localeCompare(a.paid_on) },
}

type Order = keyof typeof orders

function forText(entry: IncomeEntry): string {
  if (entry.source === 'addition') return `Addition: ${entry.addition!.name}`
  if (entry.source === 'retainer') return entry.collection === 'auto_transfer' ? 'Retainer, auto transfer' : 'Retainer'
  return 'Project'
}

function PaymentsTile({ entries, range }: { entries: IncomeEntry[]; range: Range }) {
  const [order, setOrder] = useState<Order>('newest')
  const sorted = [...entries].sort(orders[order].compare)

  return (
    <section className="tile span-12">
      <div className="tile-head st-head">
        <h2 className="tile-label">
          {entries.length ? `${plural(entries.length, 'payment')} ${range.phrase}` : 'Payments'}
        </h2>
        {entries.length > 1 && (
          <Segmented role="group" aria-label="Order payments" className="st-view">
            {(Object.keys(orders) as Order[]).map((key) => (
              <button key={key} type="button" aria-pressed={order === key} onClick={() => setOrder(key)}>
                {orders[key].label}
              </button>
            ))}
          </Segmented>
        )}
      </div>
      {entries.length === 0 ? (
        <NoData>Nothing received {range.phrase}.</NoData>
      ) : (
        <div className="st-scroll st-payments">
          <table className="st-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Client</th>
                <th>For</th>
                <th className="num">Amount</th>
              </tr>
            </thead>
            <tbody>
              {sorted.map((entry, i) => (
                <tr key={i}>
                  <td className="nowrap st-pay-date">{formatDay(entry.paid_on, { year: true })}</td>
                  <td className="st-pay-client">
                    <Link to={`/clients/${entry.client.id}`}>{entry.client.name}</Link>
                  </td>
                  <td className="st-pay-for">
                    <span className="st-for">
                      <i style={{ background: sourceColor(entry.source) }} aria-hidden="true" />
                      <span>
                        {entry.project ? <Link to={`/projects/${entry.project.id}`}>{entry.project.name}</Link> : 'No project'}
                        <small>
                          {forText(entry)}
                          {entry.late && `, ${plural(entry.days_late!, 'day')} late`}
                        </small>
                      </span>
                    </span>
                  </td>
                  <td className="num strong st-pay-amount">{formatNTD(entry.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
