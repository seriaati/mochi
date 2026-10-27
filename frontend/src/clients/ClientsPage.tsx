import { useState } from 'react'
import { useNavigate } from 'react-router'
import { AddButton } from '../components/AddButton.tsx'
import { Skeleton, type Bone } from '../components/Skeleton.tsx'
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

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Clients</h1>
          {clients.data && (
            <p className="page-sub">
              {all.length} {all.length === 1 ? 'client' : 'clients'}
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
          <AddButton label="Add client" onClick={() => setAdding(true)} />
        </div>
      </div>

      {clients.isPending && (
        <Skeleton className="client-grid" label="Loading clients" tiles={Array<Bone>(6).fill({ height: 168 })} />
      )}
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
