import type { Project } from './queries.ts'
import { elapsedPercent } from './schedule.ts'

/** Schedule progress: elapsed share of start → due, full and green once delivered. */
export function Track({ project }: { project: Project }) {
  const percent = elapsedPercent(project)
  if (percent === null) return <div className="track open" role="img" aria-label="No due date" />
  return (
    <div
      className="track"
      role="progressbar"
      aria-label={project.delivered_on ? 'Delivered' : 'Time elapsed'}
      aria-valuenow={percent}
    >
      <i className={project.delivered_on ? 'good' : undefined} style={{ width: `${percent}%` }} />
    </div>
  )
}
