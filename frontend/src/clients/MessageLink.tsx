import { contactKinds, contactUrl } from './contactKinds.ts'
import type { Contact } from './queries.ts'

/** A button that opens a conversation with them on the contact's platform; nothing without a link. */
export function MessageLink({ contact, className = 'btn secondary' }: { contact: Contact | null | undefined; className?: string }) {
  const url = contact && contactUrl(contact)
  if (!contact || !url) return null
  // Web links open in a new tab; mailto: opens the mail app as it is.
  const web = url.startsWith('https:')
  return (
    <a className={className} href={url} target={web ? '_blank' : undefined} rel={web ? 'noreferrer' : undefined}>
      {contactKinds[contact.kind].message}
    </a>
  )
}
