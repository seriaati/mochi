import type { Contact, ContactKind } from './queries.ts'

/** message: the button that opens a conversation with them there, for contactUrl. */
export const contactKinds: Record<ContactKind, { label: string; icon: string; field: string; message: string }> = {
  discord: { label: 'Discord', icon: 'DC', field: 'Username', message: 'Message on Discord' },
  line: { label: 'LINE', icon: 'LN', field: 'LINE ID', message: 'Message on LINE' },
  email: { label: 'Email', icon: '@', field: 'Email address', message: 'Send an email' },
  other: { label: 'Other', icon: '•••', field: 'Contact', message: '' },
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

/**
 * Where to talk to them: a Discord profile, with Message on it (the closest a link gets to your
 * DM, whose own link needs a channel ID only your Discord account can see), LINE's add-friend
 * page for their ID, or a new email. Null when there's nowhere to link: a Discord contact
 * without a user ID, or "other".
 */
export function contactUrl(contact: Contact): string | null {
  switch (contact.kind) {
    case 'discord':
      return contact.discord_user_id && `https://discord.com/users/${contact.discord_user_id}`
    case 'line':
      return `https://line.me/ti/p/~${encodeURIComponent(contact.value)}`
    case 'email':
      return `mailto:${contact.value}`
    case 'other':
      return null
  }
}

/** The contact to message a client on: their linked Discord contact, else the first with a link. */
export function messageContact(contacts: Contact[]): Contact | undefined {
  const discord = discordContact(contacts)
  if (discord?.discord_user_id) return discord
  return contacts.find((c) => contactUrl(c) !== null)
}
