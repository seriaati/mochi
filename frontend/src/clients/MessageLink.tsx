import type { ReactNode } from 'react'
import { contactKinds, contactUrl } from './contactKinds.ts'
import { KindLabel } from './KindLabel.tsx'
import type { Contact } from './queries.ts'

type Props = {
  contact: Contact | null | undefined
  className?: string
  /** The button's text, in place of "Message on <platform>". */
  children?: ReactNode
}

/** A button that opens a conversation with them on the contact's platform; nothing without a link. */
export function MessageLink({ contact, className = 'btn secondary', children }: Props) {
  const url = contact && contactUrl(contact)
  if (!contact || !url) return null
  // Web links open in a new tab; mailto: opens the mail app as it is.
  const web = url.startsWith('https:')
  return (
    <a className={className} href={url} target={web ? '_blank' : undefined} rel={web ? 'noreferrer' : undefined}>
      {children ??
        (contact.kind === 'email' ? (
          contactKinds.email.message
        ) : (
          <>
            Message on <KindLabel kind={contact.kind} />
          </>
        ))}
    </a>
  )
}
