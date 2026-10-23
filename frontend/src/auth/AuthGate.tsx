import type { ReactNode } from 'react'
import { LoginPage } from './LoginPage.tsx'
import { useSession } from './queries.ts'

/** Renders the app only once the session check says this browser is logged in. */
export function AuthGate({ children }: { children: ReactNode }) {
  const session = useSession()
  if (session.isPending) return null
  if (session.data?.authenticated) return children
  return <LoginPage checkError={session.error?.message} />
}
