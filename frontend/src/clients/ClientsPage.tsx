import { useState } from 'react'
import { useNavigate } from 'react-router'
import { ClientCard } from './ClientCard.tsx'
import { ClientDialog } from './ClientDialog.tsx'
import { contactHandle } from './contactKinds.ts'
import { useClients, type Client } from './queries.ts'
import './ClientsPage.css'

function matches(client: Client, query: string) {
  const haystack = [
    client.name,
    client.contact_person,
    client.discord_name,
    ...client.contacts.flatMap((c) => [c.value, contactHandle(c)]),
  ]
  return haystack.some((text) => text?.toLowerCase().includes(query))
}

export function ClientsPage() {
  const clients = useClients()
  const [query, setQuery] = useState('')
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()

  const all = clients.data ?? []
  const shown = all.filter((c) => matches(c, query.trim().toLowerCase()))
  const onDiscord = all.filter((c) => c.contacts.some((m) => m.kind === 'discord')).length

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Clients</h1>
          {clients.data && (
            <p className="page-sub">
              <i className="discord-dot" />
              {all.length} {all.length === 1 ? 'client' : 'clients'} · {onDiscord} on Discord
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
              placeholder="Search clients"
              aria-label="Search clients"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <button className="btn" type="button" onClick={() => setAdding(true)}>
            Add client
          </button>
        </div>
      </div>

      {clients.isPending && <p className="status">Loading clients…</p>}
      {clients.error && <p className="status">Couldn't load clients: {clients.error.message}</p>}
      {clients.data && all.length === 0 && (
        <section className="tile">No clients yet. Add your first one to get started.</section>
      )}
      {all.length > 0 && shown.length === 0 && <p className="status">No clients match “{query}”.</p>}

      <div className="client-grid">
        {shown.map((client) => (
          <ClientCard key={client.id} client={client} />
        ))}
      </div>

      {adding && (
        <ClientDialog
          onClose={() => setAdding(false)}
          onSaved={(client) => navigate(`/clients/${client.id}`)}
        />
      )}
    </>
  )
}
