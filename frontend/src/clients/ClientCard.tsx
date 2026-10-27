import { Link } from 'react-router'
import { Avatar } from '../components/Avatar.tsx'
import { DiscordLogo } from '../components/PlatformLogo.tsx'
import { formatNTD, initials } from '../format.ts'
import { dueLabel } from '../maintenance/labels.ts'
import { useAvatarTint } from '../tint.ts'
import { contactHandle } from './contactKinds.ts'
import { KindLabel } from './KindLabel.tsx'
import type { Client } from './queries.ts'

export function ClientCard({ client }: { client: Client }) {
  const hasDiscord = client.contacts.some((c) => c.kind === 'discord')
  const projects = client.project_count
  const tint = useAvatarTint(client.id, client.avatar_url)

  return (
    <Link className={`client-card ${tint}`} to={`/clients/${client.id}`}>
      <div className="client-card-head">
        <Avatar className="client-avatar" src={client.avatar_url} fallback={initials(client.name)}>
          {hasDiscord && (
            <span className="discord-badge" title="On Discord">
              <DiscordLogo aria-label="On Discord" />
            </span>
          )}
        </Avatar>
        <div>
          <h2 className="client-name">{client.name}</h2>
          {client.contact_person && <p className="client-person">{client.contact_person}</p>}
        </div>
        <MaintenanceFlag client={client} />
      </div>

      {client.contacts.length > 0 && (
        <ul className="contact-pills">
          {client.contacts.map((contact) => (
            <li key={contact.id}>
              <b>
                <KindLabel kind={contact.kind} />
              </b>
              {contactHandle(contact)}
            </li>
          ))}
        </ul>
      )}

      <dl className="client-stats">
        <div>
          <dt>{projects === 1 ? 'project' : 'projects'}</dt>
          <dd>{projects}</dd>
        </div>
        <div>
          <dt>lifetime</dt>
          <dd>{formatNTD(client.lifetime_billed)}</dd>
        </div>
        <div>
          <dt>{client.monthly_maintenance ? 'per month' : 'no retainer'}</dt>
          <dd>{client.monthly_maintenance ? formatNTD(client.monthly_maintenance) : '—'}</dd>
        </div>
      </dl>
    </Link>
  )
}

/** "Overdue", "Due Sun" or "Auto‑pay" for the client's monthly maintenance. */
function MaintenanceFlag({ client }: { client: Client }) {
  switch (client.maintenance_flag) {
    case 'overdue':
      return <span className="client-flag late">Overdue</span>
    case 'due':
      return <span className="client-flag">{dueLabel(client.maintenance_due_on!)}</span>
    case 'auto':
      return <span className="client-flag">Auto‑pay</span>
    default:
      return null
  }
}
