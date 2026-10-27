import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { Avatar } from '../components/Avatar.tsx'
import { formatMonth, initials, timeAgo } from '../format.ts'
import { ClientMaintenanceTile } from '../maintenance/ClientMaintenanceTile.tsx'
import { ClientMoneyTile, ClientProjectsTile } from '../projects/ClientProjectTiles.tsx'
import { useAvatarTint } from '../tint.ts'
import { ClientDialog } from './ClientDialog.tsx'
import { ContactDialog } from './ContactDialog.tsx'
import { KindLabel } from './KindLabel.tsx'
import { contactHandle, contactKinds, discordContact, messageContact } from './contactKinds.ts'
import { MessageLink } from './MessageLink.tsx'
import { useClient, useDeleteClient, useSyncDiscord, type Client, type Contact, type DiscordProfile } from './queries.ts'
import './ClientDetailPage.css'

export function ClientDetailPage() {
  const id = Number(useParams().id)
  const client = useClient(id)

  return (
    <>
      <Link className="back" to="/clients">
        ← Clients
      </Link>
      {client.isPending && <p className="status">Loading client…</p>}
      {client.error && <p className="status">Couldn't load this client: {client.error.message}</p>}
      {client.data && <ClientTiles client={client.data} />}
    </>
  )
}

function ClientTiles({ client }: { client: Client }) {
  const [editing, setEditing] = useState(false)

  return (
    <div className="bento">
      <HeroTile client={client} onEdit={() => setEditing(true)} />

      <ClientMoneyTile client={client} />
      <ClientProjectsTile client={client} />

      <ContactTile client={client} />

      <ClientMaintenanceTile client={client} />

      {editing && <ClientDialog client={client} onClose={() => setEditing(false)} />}
    </div>
  )
}

function HeroTile({ client, onEdit }: { client: Client; onEdit: () => void }) {
  // The Contact tile shows their handle; here, only where the name and avatar come from.
  const profile = discordContact(client.contacts)?.discord_profile
  const reach = messageContact(client.contacts)
  const since = `client since ${formatMonth(client.created_at)}`
  const remove = useDeleteClient(client.id)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const navigate = useNavigate()
  const tint = useAvatarTint(client.id, client.avatar_url)

  return (
    <section className={`tile span-8 client-hero ${tint}`}>
      <div className="client-hero-head">
        <Avatar className="client-hero-avatar" src={client.avatar_url} fallback={initials(client.name)} />
        <div>
          <h1 className="client-hero-name">{client.name}</h1>
          <p className="client-hero-since">
            {client.contact_person ? `${client.contact_person} · ${since}` : since}
          </p>
        </div>
      </div>
      {client.notes && <p className="client-hero-notes">{client.notes}</p>}
      {profile && <DiscordSync clientId={client.id} profile={profile} />}
      <div className="client-hero-actions">
        <MessageLink contact={reach} className="btn" />
        <button className={reach ? 'btn secondary' : 'btn'} type="button" onClick={onEdit}>
          Edit client
        </button>
        <button
          className="btn danger"
          type="button"
          disabled={remove.isPending}
          onClick={() =>
            confirmingDelete
              ? remove.mutate(undefined, { onSuccess: () => navigate('/clients') })
              : setConfirmingDelete(true)
          }
        >
          {confirmingDelete ? 'Confirm delete' : 'Delete'}
        </button>
      </div>
      {remove.error && <p className="form-error client-hero-note">{remove.error.message}</p>}
      {confirmingDelete && !remove.error && (
        <p className="client-hero-note">This also removes the client&rsquo;s contact methods.</p>
      )}
    </section>
  )
}

/** Where the client's name and avatar come from, when they last synced, and Sync now. */
function DiscordSync({ clientId, profile }: { clientId: number; profile: DiscordProfile }) {
  const sync = useSyncDiscord(clientId)

  return (
    <p className="client-hero-sync">
      <span>{syncLabel(profile)}</span>
      {profile.status === 'off' ? (
        <Link to="/settings#discord">Add a bot token</Link>
      ) : (
        <button className="link-btn" type="button" disabled={sync.isPending} onClick={() => sync.mutate()}>
          {sync.isPending ? 'Syncing…' : 'Sync now'}
        </button>
      )}
      {sync.error && <small className="client-hero-sync-error">{sync.error.message}</small>}
    </p>
  )
}

function syncLabel(profile: DiscordProfile): string {
  switch (profile.status) {
    case 'ok':
      return `Name and avatar synced from Discord ${timeAgo(profile.synced_at!)}`
    case 'not_found':
      return 'Discord has no user with this ID'
    case 'error':
      return "Couldn't sync from Discord"
    case 'pending':
      return 'Not synced from Discord yet'
    case 'off':
      return 'Discord sync is off'
  }
}

function ContactTile({ client }: { client: Client }) {
  // undefined = closed, null = adding, a contact = editing it.
  const [dialog, setDialog] = useState<Contact | null>()

  return (
    <section className="tile span-4">
      <div className="tile-head">
        <h2 className="tile-label">Contact</h2>
        <button className="link-btn" type="button" onClick={() => setDialog(null)}>
          Add
        </button>
      </div>
      {client.contacts.length === 0 && <p className="empty-note">No contact methods yet.</p>}
      <ul className="contact-list">
        {client.contacts.map((contact) => (
          <li key={contact.id}>
            <button
              className="contact-row"
              type="button"
              aria-label={`Edit ${contactKinds[contact.kind].label} contact ${contactHandle(contact)}`}
              onClick={() => setDialog(contact)}
            >
              <Avatar
                className={`contact-icon kind-${contact.kind}`}
                src={contact.discord_profile?.avatar_url}
                fallback={contactKinds[contact.kind].icon ?? <KindLabel kind={contact.kind} />}
              />
              <span>
                <b>{contactKinds[contact.kind].label}</b>
                <small>{contactHandle(contact)}</small>
              </span>
            </button>
          </li>
        ))}
      </ul>
      {dialog !== undefined && (
        <ContactDialog
          clientId={client.id}
          contact={dialog ?? undefined}
          onClose={() => setDialog(undefined)}
        />
      )}
    </section>
  )
}
