import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { AddButton } from '../components/AddButton.tsx'
import { Segmented } from '../components/Segmented.tsx'
import { Select } from '../components/Select.tsx'
import { Skeleton, type Bone } from '../components/Skeleton.tsx'
import { formatNumber, formatNTD, plural, todayISO } from '../format.ts'
import { ProjectCard } from './ProjectCard.tsx'
import { ProjectDialog } from './ProjectDialog.tsx'
import { useProjects, type Project } from './queries.ts'
import './ProjectsPage.css'

const filters = {
  all: { label: 'All', test: () => true },
  open: { label: 'In progress', test: (p: Project) => p.status !== 'done' },
  unpaid: { label: 'Unpaid', test: (p: Project) => p.total_outstanding > 0 },
  done: { label: 'Done', test: (p: Project) => p.status === 'done' },
}

type Filter = keyof typeof filters

const matches = (project: Project, query: string) =>
  [project.name, project.client.name].some((text) => text.toLowerCase().includes(query))

// Unfinished projects come first under either order. ISO dates compare as strings.
const sorts = {
  due: {
    label: 'Sort by due date',
    compare: (a: Project, b: Project) =>
      Number(a.due_on === null) - Number(b.due_on === null) ||
      (a.due_on ?? '').localeCompare(b.due_on ?? ''),
  },
  start: {
    label: 'Sort by start date',
    compare: (a: Project, b: Project) => b.started_on.localeCompare(a.started_on),
  },
}

type Sort = keyof typeof sorts

const byDone = (a: Project, b: Project) =>
  Number(a.status === 'done') - Number(b.status === 'done')

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)

export function ProjectsPage() {
  const projects = useProjects()
  const [filter, setFilter] = useState<Filter>('all')
  const [sort, setSort] = useState<Sort>('start')
  // By the year a project started; 'all' shows every year.
  const [startYear, setStartYear] = useState('all')
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()

  const all = projects.data ?? []
  const years = [...new Set(all.map((p) => p.started_on.slice(0, 4)))].sort().reverse()
  const q = query.trim().toLowerCase()
  // The year and search narrow the list; the counts beside each filter follow them.
  const narrowed = all.filter(
    (p) => (startYear === 'all' || p.started_on.startsWith(startYear)) && matches(p, q),
  )
  const shown = narrowed
    .filter(filters[filter].test)
    .sort((a, b) => byDone(a, b) || sorts[sort].compare(a, b))
  const year = todayISO().slice(0, 4)
  const open = all.filter(filters.open.test)
  const doneThisYear = all.filter((p) => p.status === 'done' && p.delivered_on?.startsWith(year))

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Projects</h1>
          {projects.data && (
            <p className="page-sub">
              {open.length} in progress · {doneThisYear.length} done this year
            </p>
          )}
        </div>
        <div className="page-actions">
          <label className="search">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            <input
              type="search"
              placeholder="Search projects"
              aria-label="Search projects"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <AddButton label="New project" onClick={() => setAdding(true)} />
        </div>
      </div>

      <div className="project-toolbar">
        <Segmented role="group" aria-label="Filter projects">
          {(Object.keys(filters) as Filter[]).map((key) => (
            <button
              key={key}
              type="button"
              aria-pressed={filter === key}
              onClick={() => setFilter(key)}
            >
              {filters[key].label}
              <span>{narrowed.filter(filters[key].test).length}</span>
            </button>
          ))}
        </Segmented>
        <div className="project-select project-year">
          <Select
            aria-label="Filter projects by start year"
            value={startYear}
            onChange={setStartYear}
            options={[
              { value: 'all', label: 'All years' },
              ...years.map((year) => ({ value: year, label: year })),
            ]}
          />
        </div>
        <div className="project-select project-sort">
          <Select
            aria-label="Sort projects"
            value={sort}
            onChange={setSort}
            options={(Object.keys(sorts) as Sort[]).map((key) => ({
              value: key,
              label: sorts[key].label,
            }))}
          />
        </div>
      </div>

      {projects.isPending && (
        <Skeleton
          label="Loading projects"
          tiles={[
            ...Array<Bone>(3).fill({ span: 'span-4', height: 132 }),
            ...Array<Bone>(4).fill({ span: 'span-6', height: 300 }),
          ]}
        />
      )}
      {projects.error && <p className="status">Couldn't load projects: {projects.error.message}</p>}

      {projects.data && (
        <div className="bento">
          <Summary projects={all} year={year} onUnpaid={() => setFilter('unpaid')} />
          {all.length === 0 && (
            <section className="tile span-12">No projects yet. Start one with New project.</section>
          )}
          {all.length > 0 && shown.length === 0 && (
            <p className="status span-12">
              No {filter === 'all' ? '' : `${filters[filter].label.toLowerCase()} `}projects
              {startYear === 'all' ? '' : ` started in ${startYear}`}
              {q ? ` match “${query.trim()}”` : ''}.
            </p>
          )}
          {shown.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}

      {adding && (
        <ProjectDialog
          onClose={() => setAdding(false)}
          onSaved={(project) => navigate(`/projects/${project.id}`)}
        />
      )}
    </>
  )
}

type SummaryProps = { projects: Project[]; year: string; onUnpaid: () => void }

function Summary({ projects, year, onUnpaid }: SummaryProps) {
  const open = projects.filter(filters.open.test)
  const additions = projects.flatMap((p) => p.additions.filter((a) => a.agreed_on.startsWith(year)))
  const withAdditions = new Set(additions.map((a) => a.project_id)).size

  return (
    <>
      <SummaryTile tint="sage" label="In progress" amount={sum(open.map((p) => p.total))}>
        {formatNTD(sum(open.map((p) => p.total_paid)))} received so far
      </SummaryTile>
      <SummaryTile
        tint="peach"
        label="Waiting to be paid"
        amount={sum(projects.map((p) => p.total_outstanding))}
        onClick={onUnpaid}
      >
        Final payments and unpaid additions
      </SummaryTile>
      <SummaryTile
        tint="lavender"
        label={`Additions in ${year}`}
        amount={sum(additions.map((a) => a.price))}
      >
        {additions.length
          ? `${plural(additions.length, 'addition')} across ${plural(withAdditions, 'project')}`
          : 'None yet this year'}
      </SummaryTile>
    </>
  )
}

type SummaryTileProps = {
  tint: string
  label: string
  amount: number
  children: ReactNode
  /** Makes the whole tile a button, e.g. to filter the list to what it counts. */
  onClick?: () => void
}

function SummaryTile({ tint, label, amount, children, onClick }: SummaryTileProps) {
  const body = (
    <>
      <h2 className="tile-label">{label}</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(amount)}
      </p>
      <p className="summary-meta">{children}</p>
    </>
  )
  const className = `tile span-4 summary-tile tint-${tint}`
  if (!onClick) return <section className={className}>{body}</section>
  return (
    <button className={`${className} summary-button`} type="button" onClick={onClick}>
      {body}
    </button>
  )
}
