import { Link } from 'react-router'
import { Avatar } from '../components/Avatar.tsx'
import { formatDay, formatNTD, initials, plural } from '../format.ts'
import { tintClass } from '../tint.ts'
import type { Project } from './queries.ts'
import { daysIn, scheduleChip } from './schedule.ts'
import { Track } from './Track.tsx'

export function ProjectCard({ project }: { project: Project }) {
  const chip = scheduleChip(project)
  const done = project.status === 'done'
  const muted = done ? ' muted' : ''
  const additions = project.additions.length
  // Additions still owed on a finished project, e.g. "Giveaway feature · NT$500 unpaid".
  const unpaid = done ? project.additions.filter((a) => a.outstanding > 0) : []

  return (
    <Link className="tile span-6 project-card" to={`/projects/${project.id}`}>
      <div className="project-card-head">
        <Avatar
          className={`project-avatar ${tintClass(project.client.id)}`}
          src={project.client.avatar_url}
          fallback={initials(project.client.name)}
        />
        <div className="project-card-client">
          <b>{project.client.name}</b>
          {project.client.contact_person}
        </div>
        <span className={`chip ${chip.tone}`}>{chip.label}</span>
      </div>

      <h2 className={`project-card-name${muted}`}>{project.name}</h2>
      <div className={`project-card-track${muted}`}>
        <Track project={project} />
      </div>
      <div className="project-dates">
        {project.delivered_on ? (
          <>
            <span>{formatDay(project.started_on)}</span>
            <span>Delivered {formatDay(project.delivered_on)}</span>
          </>
        ) : project.due_on ? (
          <>
            <span>{formatDay(project.started_on)}</span>
            <span>Due {formatDay(project.due_on)}</span>
          </>
        ) : (
          <>
            <span>Started {formatDay(project.started_on)}</span>
            <span>{plural(daysIn(project), 'day')} in</span>
          </>
        )}
      </div>

      <dl className={`project-money${muted}`}>
        <div>
          <dt>Price</dt>
          <dd>{formatNTD(project.price)}</dd>
        </div>
        <div className={additions ? 'added' : undefined}>
          <dt>{additions ? plural(additions, 'addition') : 'Additions'}</dt>
          <dd>{additions ? `+${formatNTD(project.additions_total)}` : '—'}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>{formatNTD(project.total)}</dd>
        </div>
      </dl>

      <SplitBar project={project} muted={done} />
      <SplitLabel project={project} />

      {unpaid.map((addition) => (
        <p key={addition.id} className="project-flag">
          {addition.name} · {formatNTD(addition.outstanding)} unpaid
        </p>
      ))}
    </Link>
  )
}

/** Deposit | final, sized by the deposit percentage; a part turns green once paid. */
function SplitBar({ project, muted }: { project: Project; muted: boolean }) {
  const pct = project.deposit_percent
  const split = pct > 0 && pct < 100
  return (
    <div
      className={`split-bar${muted ? ' muted' : ''}`}
      style={{ gridTemplateColumns: split ? `${pct}fr ${100 - pct}fr` : '1fr' }}
      aria-hidden="true"
    >
      {split && <i className={project.deposit_due === 0 ? 'on' : undefined} />}
      <i className={project.outstanding === 0 ? 'on' : undefined} />
    </div>
  )
}

function SplitLabel({ project }: { project: Project }) {
  const split = project.expected_deposit > 0 && project.expected_final > 0
  const onDelivery = project.delivered_on ? 'due now' : 'on delivery'

  if (project.outstanding === 0) {
    return (
      <p className="split-label">
        <span>
          <b>{split ? 'Deposit + final' : 'Paid in full'}</b>
          {split && ' · paid'}
        </span>
        <span>{project.delivered_on ? formatNTD(project.price) : 'Not delivered yet'}</span>
      </p>
    )
  }
  if (!split) {
    const upFront = project.deposit_percent === 100
    return (
      <p className="split-label">
        <b>{upFront ? 'Paid up front' : 'Single payment'}</b>
        <span className="due">
          {formatNTD(project.outstanding)} {upFront ? 'due' : onDelivery}
        </span>
      </p>
    )
  }
  return (
    <p className="split-label">
      <span>
        <b>Deposit {project.deposit_percent}%</b> ·{' '}
        {project.deposit_due === 0 ? 'paid' : `${formatNTD(project.deposit_due)} due`}
      </span>
      <span className="due">
        Final {formatNTD(project.final_due)} {onDelivery}
      </span>
    </p>
  )
}
