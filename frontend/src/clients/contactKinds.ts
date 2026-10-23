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
