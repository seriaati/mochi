import { useState } from 'react'
import { Link, useNavigate } from 'react-router'
import type { Client } from '../clients/queries.ts'
import { formatDay, formatNTD, plural } from '../format.ts'
import { useClientRetainers } from '../maintenance/queries.ts'
import { ProjectDialog } from './ProjectDialog.tsx'
import { useClientProjects, type Project } from './queries.ts'
import { statusLabels } from './schedule.ts'
import { Track } from './Track.tsx'
import './ClientProjectTiles.css'

const sum = (values: number[]) => values.reduce((a, b) => a + b, 0)

/** Dark span-4 tile on the client page: billed, paid and outstanding, plus maintenance received. */
export function ClientMoneyTile({ client }: { client: Client }) {
  const projects = useClientProjects(client.id).data ?? []
  const retainers = useClientRetainers(client.id).data ?? []
  const outstanding = sum(projects.map((p) => p.total_outstanding))

  return (
    <section className="tile ink span-4">
      <h2 className="tile-label">Billed, all time</h2>
      <p className="big-number">{formatNTD(client.lifetime_billed)}</p>
      <dl className="money-lines">
        <div>
          <dt>Projects paid</dt>
          <dd>{formatNTD(sum(projects.map((p) => p.total_paid)))}</dd>
        </div>
        <div className={outstanding > 0 ? 'due' : undefined}>
          <dt>Outstanding</dt>
          <dd>{formatNTD(outstanding)}</dd>
        </div>
        {retainers.length > 0 && (
          <div className="money-maintenance">
            <dt>Maintenance received</dt>
            <dd>{formatNTD(sum(retainers.map((r) => r.received)))}</dd>
          </div>
        )}
      </dl>
    </section>
  )
}

/** Span-8 tile on the client page listing the client's projects. */
export function ClientProjectsTile({ client }: { client: Client }) {
  const projects = useClientProjects(client.id)
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()

  return (
    <section className="tile span-8">
      <div className="tile-head">
        <h2 className="tile-label">Projects</h2>
        <button className="link-btn" type="button" onClick={() => setAdding(true)}>
          New project
        </button>
      </div>
      {projects.error && <p className="empty-note">Couldn't load projects: {projects.error.message}</p>}
      {projects.data?.length === 0 && <p className="empty-note">No projects for this client yet.</p>}
      {projects.data && projects.data.length > 0 && (
        <ul className="client-project-list">
          {projects.data.map((project) => (
            <li key={project.id}>
              <ClientProjectRow project={project} />
            </li>
          ))}
        </ul>
      )}
      {adding && (
        <ProjectDialog
          clientId={client.id}
          onClose={() => setAdding(false)}
          onSaved={(project) => navigate(`/projects/${project.id}`)}
        />
      )}
    </section>
  )
}

function ClientProjectRow({ project }: { project: Project }) {
  const additions = project.additions.length
  const end = project.delivered_on ?? project.due_on
  const status = statusLabels[project.status] + (additions ? ` · ${plural(additions, 'addition')}` : '')

  return (
    <Link className="client-project" to={`/projects/${project.id}`}>
      <div>
        <b>{project.name}</b>
        <small>{status}</small>
      </div>
      <div>
        <Track project={project} />
        <p className="client-project-when">
          {end
            ? `${formatDay(project.started_on)} – ${formatDay(end, { year: true })}`
            : `Since ${formatDay(project.started_on, { year: true })} · no due date`}
        </p>
      </div>
      <p className="client-project-total">
        {formatNTD(project.total)}
        {project.total_outstanding > 0 ? (
          <small className="due">{formatNTD(project.total_outstanding)} due</small>
        ) : (
          <small className="paid">Paid</small>
        )}
      </p>
    </Link>
  )
}
