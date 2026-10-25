import { useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type FormEvent } from 'react'
import { savedStudio } from '../studio.ts'
import { clearCache, useLogin } from './queries.ts'
import './LoginPage.css'

/** The password screen. `checkError` is why the session check failed, e.g. the API is down. */
export function LoginPage({ checkError }: { checkError?: string }) {
  const queryClient = useQueryClient()
  const login = useLogin()
  const [password, setPassword] = useState('')
  const [studio] = useState(savedStudio)

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
          {studio?.studio_logo ? <img className="brand-logo" src={studio.studio_logo} alt="" /> : <i />}
          <span>{studio?.studio_name ?? 'Studio'}</span>
        </div>
        <h1 className="login-title">Welcome back</h1>
        <p className="login-sub">Enter your password to open the dashboard.</p>
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
