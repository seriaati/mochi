import { useSearchParams } from 'react-router'
import '../auth/LoginPage.css'
import './AuthorizePage.css'
import { useAccessRequest, useAnswer } from './queries.ts'

/**
 * Where an MCP client's OAuth sign-in (see backend/app/oauth.py) asks the user to approve it.
 * Shown only when logged in: AuthGate puts the login screen first.
 */
export function AuthorizePage() {
  const [params] = useSearchParams()
  const id = params.get('request') ?? ''
  const request = useAccessRequest(id)
  const answer = useAnswer(id)

  const name = request.data?.client_name ?? 'An app'
  // Disabled from the click until the browser has left for the client.
  const busy = answer.isPending || answer.isSuccess

  return (
    <main className="login">
      <section className="tile login-tile">
        <div className="brand">
          <i />
          Studio
        </div>
        {request.isPending ? null : request.isError ? (
          <>
            <h1 className="login-title">Can't connect</h1>
            <p className="login-sub">{request.error.message}</p>
          </>
        ) : (
          <>
            <h1 className="login-title">Connect {name}?</h1>
            <p className="login-sub">
              It will be able to see and change everything in your dashboard: clients, projects,
              payments and maintenance fees. It can also send reminders to your Discord.
            </p>
            <p className="consent-host">
              Access goes to
              <strong title={request.data.redirect_uri}>{hostOf(request.data.redirect_uri)}</strong>
            </p>
            {answer.isError && (
              <p className="form-error consent-error" role="alert">
                {answer.error.message}
              </p>
            )}
            <div className="consent-actions">
              <button
                className="btn secondary"
                type="button"
                disabled={busy}
                onClick={() => answer.mutate(false)}
              >
                Deny
              </button>
              <button className="btn" type="button" disabled={busy} onClick={() => answer.mutate(true)}>
                {busy && answer.variables ? 'Connecting…' : 'Allow'}
              </button>
            </div>
          </>
        )}
      </section>
    </main>
  )
}

function hostOf(uri: string): string {
  try {
    return new URL(uri).host
  } catch {
    return uri
  }
}
