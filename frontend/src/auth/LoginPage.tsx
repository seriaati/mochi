import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { MochiMark } from '../components/MochiMark.tsx'
import { clearCache, useLogin } from './queries.ts'
import './LoginPage.css'

/** Set only on the public demo's build: the screen then gives the password and fills it in. */
const DEMO_PASSWORD = import.meta.env.VITE_DEMO_PASSWORD

/** The password screen. `checkError` is why the session check failed, e.g. the API is down. */
export function LoginPage({ checkError }: { checkError?: string }) {
  const queryClient = useQueryClient()
  const login = useLogin()
  const [password, setPassword] = useState(DEMO_PASSWORD ?? '')

  // Nothing from the last session outlives it.
  useEffect(() => clearCache(queryClient), [queryClient])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    login.mutate(password, { onError: () => setPassword('') })
  }

  const error = login.error?.message ?? (login.isIdle ? checkError : undefined)

  return (
    <main className="login">
      <section className="tile login-tile">
        <div className="brand">
          <MochiMark />
          <span>Mochi</span>
        </div>
        {DEMO_PASSWORD ? (
          <>
            <h1 className="login-title">Try Mochi</h1>
            <p className="login-sub">
              A demo with made-up data that resets every day. The password is <strong>{DEMO_PASSWORD}</strong>.
            </p>
          </>
        ) : (
          <>
            <h1 className="login-title">Welcome back</h1>
            <p className="login-sub">Enter your password to open the dashboard.</p>
          </>
        )}
        <form className="form login-form" onSubmit={submit}>
          <label className="field">
            Password
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              autoFocus
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          {error && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}
          <button className="btn" type="submit" disabled={login.isPending}>
            {login.isPending ? 'Logging in…' : 'Log in'}
          </button>
        </form>
      </section>
    </main>
  )
}
