import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { Avatar } from '../components/Avatar.tsx'
import { formatMonth, initials, timeAgo } from '../format.ts'
import { ClientMaintenanceTile } from '../maintenance/ClientMaintenanceTile.tsx'
import { useClientRetainers } from '../maintenance/queries.ts'
import { ClientMoneyTile, ClientProjectsTile } from '../projects/ClientProjectTiles.tsx'
import { tintClass } from '../tint.ts'
import { ClientDialog } from './ClientDialog.tsx'
import { ContactDialog } from './ContactDialog.tsx'
import { contactHandle, contactKinds } from './contactKinds.ts'
import { useClient, useSyncDiscord, type Client, type Contact, type DiscordProfile } from './queries.ts'
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
  // The synced Discord contact the avatar comes from, else the first one.
  const discord =
    client.contacts.find((c) => c.discord_profile?.status === 'ok') ??
    client.contacts.find((c) => c.kind === 'discord')
  const since = `client since ${formatMonth(client.created_at)}`

  return (
    <section className={`tile span-8 client-hero ${tintClass(client.id)}`}>
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
      {discord && <DiscordCard clientId={client.id} contact={discord} />}
      <div className="client-hero-actions">
        <button className="btn" type="button" onClick={onEdit}>
          Edit client
        </button>
      </div>
    </section>
  )
}

/** The client's Discord profile: synced name and @username, or the typed handle and ID. */
function DiscordCard({ clientId, contact }: { clientId: number; contact: Contact }) {
  const sync = useSyncDiscord(clientId)
  const profile = contact.discord_profile
  const name = profile?.display_name

  return (
    <div className="discord-card">
      <Avatar className="discord-avatar" src={profile?.avatar_url} fallback={initials(name ?? contact.value)} />
      <div>
        <b>{name ?? contact.value}</b>
        <small>
          {name
            ? `${contactHandle(contact)} on Discord`
            : contact.discord_user_id
              ? `Discord · ID ${contact.discord_user_id}`
              : 'Discord'}
        </small>
      </div>
      {profile && (
        <div className="discord-sync">
          <span title={profile.status === 'off' ? 'Set DISCORD_BOT_TOKEN in backend/.env to sync names and avatars' : undefined}>
            {syncLabel(profile)}
          </span>
          {profile.status !== 'off' && (
            <button className="link-btn" type="button" disabled={sync.isPending} onClick={() => sync.mutate()}>
              {sync.isPending ? 'Syncing…' : 'Sync now'}
            </button>
          )}
          {sync.error && <small className="discord-sync-error">{sync.error.message}</small>}
        </div>
      )}
    </div>
  )
}

function syncLabel(profile: DiscordProfile): string {
  switch (profile.status) {
    case 'ok':
      return `Synced ${timeAgo(profile.synced_at!)}`
    case 'not_found':
      return 'User not found'
    case 'error':
      return 'Sync failed'
    case 'pending':
      return 'Not synced yet'
    case 'off':
      return 'Sync off'
  }
}

function ContactTile({ client }: { client: Client }) {
  // undefined = closed, null = adding, a contact = editing it.
  const [dialog, setDialog] = useState<Contact | null>()
  // Contacts that "ask" retainers, not yet ended, send their reminders to.
  const retainers = useClientRetainers(client.id).data ?? []
  const reminderContacts = new Set(
    retainers.filter((r) => r.collection === 'ask' && r.next_due_on).map((r) => r.ask_via_id),
  )

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
                fallback={contactKinds[contact.kind].icon}
              />
              <span>
                <b>{contactKinds[contact.kind].label}</b>
                <small>{contactHandle(contact)}</small>
              </span>
              {reminderContacts.has(contact.id) && <span className="contact-tag">Reminders</span>}
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
