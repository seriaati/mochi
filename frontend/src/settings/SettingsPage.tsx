import { useEffect, useState, type FormEvent } from 'react'
import { useLogout } from '../auth/queries.ts'
import { applyTheme, savedTheme, type Theme } from '../theme.ts'
import { useSaveSettings, useSettings } from './queries.ts'
import './SettingsPage.css'

const zones = Intl.supportedValuesOf('timeZone')
const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone

/** The current time, updated every few seconds. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 5_000)
    return () => clearInterval(timer)
  }, [])
  return now
}

export function SettingsPage() {
  const settings = useSettings()

  return (
    <>
      <div className="page-head">
        <div>
          <h1 className="page-title">Settings</h1>
          <p className="page-sub">Preferences for this dashboard</p>
        </div>
      </div>
      {settings.isPending && <p className="status">Loading settings…</p>}
      {settings.error && <p className="status">Couldn't load settings: {settings.error.message}</p>}
      {settings.data && (
        <div className="bento">
          <ThemeTile />
          <TimezoneTile timezone={settings.data.timezone} />
          <section className="tile span-5 tint-blue">
            <h2 className="tile-label">Discord</h2>
            <p className="settings-text">
              The webhook URL and your Discord user ID live in <code>backend/.env</code> as{' '}
              <code>DISCORD_WEBHOOK_URL</code> and <code>DISCORD_MENTION_USER_ID</code>. Restart the API after
              changing them.
            </p>
            <p className="settings-text">
              Each client gets one reminder at 09:00 on the due date in the timezone set here, then every 2
              days while anything is unpaid. A fee counts as overdue 2 days after its due date.
            </p>
            <p className="settings-text">
              With a bot token in <code>DISCORD_BOT_TOKEN</code>, clients' Discord names and avatars, and yours,
              sync from Discord every hour.
            </p>
          </section>
          <SessionTile />
        </div>
      )}
    </>
  )
}

const themes: { value: Theme; label: string }[] = [
  { value: 'system', label: 'System' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

function ThemeTile() {
  const [theme, setTheme] = useState(savedTheme)

  return (
    <section className="tile span-5 tint-yellow">
      <h2 className="tile-label">Theme</h2>
      <p className="settings-text">
        Light is Bento, dark is Bento Night. System follows this device's setting. Saved in this browser.
      </p>
      <div className="segmented settings-theme" role="group" aria-label="Theme">
        {themes.map(({ value, label }) => (
          <button
            key={value}
            type="button"
            aria-pressed={theme === value}
            onClick={() => {
              applyTheme(value)
              setTheme(value)
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </section>
  )
}

function TimezoneTile({ timezone }: { timezone: string }) {
  const save = useSaveSettings()
  const [draft, setDraft] = useState(timezone)
  const now = useNow()
  const time = now.toLocaleTimeString('en-GB', { timeZone: timezone, hour: '2-digit', minute: '2-digit' })
  const date = now.toLocaleDateString('en-GB', {
    timeZone: timezone,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    save.mutate({ timezone: draft.trim() })
  }

  function pickDevice() {
    setDraft(deviceZone)
    save.mutate({ timezone: deviceZone })
  }

  return (
    <section className="tile span-7 tint-lavender">
      <h2 className="tile-label">Timezone</h2>
      <p className="big-number">
        {time}
        <small className="settings-date">{date}</small>
      </p>
      <p className="settings-zone">
        Now in <b>{timezone}</b>. Due dates, “today” and the 09:00 reminders follow this timezone.
      </p>
      <form className="settings-form" onSubmit={submit}>
        <label className="field">
          Change timezone
          <input
            list="timezones"
            required
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            spellCheck={false}
            autoComplete="off"
          />
          <datalist id="timezones">
            {zones.map((zone) => (
              <option key={zone} value={zone} />
            ))}
          </datalist>
        </label>
        <button className="btn" type="submit" disabled={save.isPending || draft.trim() === timezone}>
          Save
        </button>
      </form>
      {deviceZone !== timezone && (
        <button className="btn secondary settings-device" type="button" disabled={save.isPending} onClick={pickDevice}>
          Use this device's timezone ({deviceZone})
        </button>
      )}
      {save.error && <p className="form-error settings-feedback">{save.error.message}</p>}
      {save.isSuccess && !save.isPending && <p className="settings-feedback settings-saved">Saved</p>}
    </section>
  )
}

function SessionTile() {
  const logout = useLogout()
  return (
    <section className="tile span-12 tint-peach settings-session">
      <div>
        <h2 className="tile-label">Session</h2>
        <p className="settings-text">
          You're logged in on this browser. A session lasts 30 days from your last visit; setting a new
          password in <code>AUTH_PASSWORD_HASH</code> logs out everywhere.
        </p>
      </div>
      <button className="btn secondary" type="button" disabled={logout.isPending} onClick={() => logout.mutate()}>
        Log out
      </button>
      {logout.error && <p className="form-error settings-feedback">{logout.error.message}</p>}
    </section>
  )
}
