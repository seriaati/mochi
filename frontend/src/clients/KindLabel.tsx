import { DiscordLogo, EmailIcon, LineLogo } from '../components/PlatformLogo.tsx'
import { contactKinds } from './contactKinds.ts'
import type { ContactKind } from './queries.ts'

/** A contact's platform by its logo, or by name for Other. */
export function KindLabel({ kind }: { kind: ContactKind }) {
  switch (kind) {
    case 'discord':
      return <DiscordLogo />
    case 'line':
      return <LineLogo />
    case 'email':
      return <EmailIcon />
    case 'other':
      return contactKinds.other.label
  }
}
