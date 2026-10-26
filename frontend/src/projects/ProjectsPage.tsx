import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { AddButton } from '../components/AddButton.tsx'
import { Segmented } from '../components/Segmented.tsx'
import { Select } from '../components/Select.tsx'
import { formatNumber, formatNTD, plural, todayISO } from '../format.ts'
import { ProjectCard } from './ProjectCard.tsx'
import { ProjectDialog } from './ProjectDialog.tsx'
import { useProjects, type Project } from './queries.ts'
import './ProjectsPage.css'

const filters = {
  all: { label: 'All', test: () => true },
  open: { label: 'In progress', test: (p: Project) => p.status !== 'done' },
  done: { label: 'Done', test: (p: Project) => p.status === 'done' },
}

type Filter = keyof typeof filters

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
  const [sort, setSort] = useState<Sort>('due')
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()

  const all = projects.data ?? []
  const shown = all
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
          <Segmented role="group" aria-label="Filter projects">
            {(Object.keys(filters) as Filter[]).map((key) => (
              <button
                key={key}
                type="button"
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {filters[key].label}
                <span>{all.filter(filters[key].test).length}</span>
              </button>
            ))}
          </Segmented>
          <div className="project-sort">
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
          <AddButton label="New project" onClick={() => setAdding(true)} />
        </div>
      </div>

      {projects.isPending && <p className="status">Loading projects…</p>}
      {projects.error && <p className="status">Couldn't load projects: {projects.error.message}</p>}

      {projects.data && (
        <div className="bento">
          <Summary projects={all} year={year} />
          {all.length === 0 && (
            <section className="tile span-12">No projects yet. Start one with New project.</section>
          )}
          {all.length > 0 && shown.length === 0 && (
            <p className="status span-12">No {filters[filter].label.toLowerCase()} projects.</p>
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

function Summary({ projects, year }: { projects: Project[]; year: string }) {
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

type SummaryTileProps = { tint: string; label: string; amount: number; children: ReactNode }

function SummaryTile({ tint, label, amount, children }: SummaryTileProps) {
  return (
    <section className={`tile span-4 summary-tile tint-${tint}`}>
      <h2 className="tile-label">{label}</h2>
      <p className="big-number">
        <small>NT$</small>
        {formatNumber(amount)}
      </p>
      <p className="summary-meta">{children}</p>
    </section>
  )
}
