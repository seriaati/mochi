import type { Contact, ContactKind } from './queries.ts'

export const contactKinds: Record<ContactKind, { label: string; icon: string; field: string }> = {
  discord: { label: 'Discord', icon: 'DC', field: 'Username' },
  line: { label: 'LINE', icon: 'LN', field: 'LINE ID' },
  email: { label: 'Email', icon: '@', field: 'Email address' },
  other: { label: 'Other', icon: '•••', field: 'Contact' },
}

/** A contact as shown: the synced Discord @username, else the handle as typed. */
export function contactHandle(contact: Contact): string {
  const username = contact.discord_profile?.username
  return username ? `@${username}` : contact.value
}

/**
 * The client's Discord contact: the first one with a user ID, else the first. Editing the client
 * sets this one's ID.
 */
export function discordContact(contacts: Contact[]): Contact | undefined {
  return contacts
    .filter((c) => c.kind === 'discord')
    .sort((a, b) => Number(a.discord_user_id === null) - Number(b.discord_user_id === null) || a.id - b.id)[0]
}
