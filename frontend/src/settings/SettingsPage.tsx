import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { applyTheme, savedTheme, type Theme } from '../theme.ts'
import { useSaveBotToken, useSaveSettings, useSettings, type Settings } from './queries.ts'
import './SettingsPage.css'

const zones = Intl.supportedValuesOf('timeZone')
const deviceZone = Intl.DateTimeFormat().resolvedOptions().timeZone

/** Longest side of a stored logo, in pixels: sharp in the top bar, and small to store. */
const LOGO_SIZE = 128

/** Shrinks an image file to fit LOGO_SIZE and returns it as a data: URL. */
async function logoDataUrl(file: File): Promise<string> {
  const url = URL.createObjectURL(file)
  try {
    const image = new Image()
    image.src = url
    await image.decode()
    if (!image.naturalWidth || !image.naturalHeight) throw new Error('No size')
    const scale = Math.min(1, LOGO_SIZE / Math.max(image.naturalWidth, image.naturalHeight))
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
    canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
    canvas.getContext('2d')!.drawImage(image, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/webp', 0.9) // PNG where the browser can't write WebP
  } finally {
    URL.revokeObjectURL(url)
  }
}

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
          <StudioTile settings={settings.data} />
          <ThemeTile />
          <TimezoneTile settings={settings.data} />
          <DiscordTile settings={settings.data} />
        </div>
      )}
    </>
  )
}

function StudioTile({ settings }: { settings: Settings }) {
  const save = useSaveSettings()
  const [logo, setLogo] = useState(settings.studio_logo)
  const [logoError, setLogoError] = useState<string>()
  const fileInput = useRef<HTMLInputElement>(null)

  async function pickLogo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    try {
      setLogo(await logoDataUrl(file))
      setLogoError(undefined)
    } catch {
      setLogoError("Couldn't read that image. Try a PNG, JPEG, WebP or SVG.")
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    save.mutate({
      ...settings,
      studio_name: form.get('studio_name') as string,
      user_name: form.get('user_name') as string,
      studio_logo: logo,
    })
  }

  return (
    <section className="tile span-7 tint-sage">
      <h2 className="tile-label">Studio</h2>
      <form className="form settings-studio" onSubmit={submit}>
        <div className="settings-logo">
          <span className="settings-logo-preview">{logo ? <img src={logo} alt="Studio logo" /> : <i />}</span>
          <button className="btn secondary" type="button" onClick={() => fileInput.current?.click()}>
            {logo ? 'Change logo' : 'Upload logo'}
          </button>
          {logo && (
            <button className="link-btn" type="button" onClick={() => setLogo(null)}>
              Remove
            </button>
          )}
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml"
            hidden
            onChange={pickLogo}
          />
        </div>
        {logoError && <p className="form-error">{logoError}</p>}
        <div className="form-row">
          <label className="field">
            Studio name
            <input name="studio_name" defaultValue={settings.studio_name ?? ''} placeholder="Studio" maxLength={60} />
          </label>
          <label className="field">
            Your name
            <input name="user_name" defaultValue={settings.user_name ?? ''} maxLength={60} autoComplete="given-name" />
          </label>
        </div>
        <p className="settings-zone">
          The top bar shows the logo and studio name. The Overview greets you by your name, or by your Discord
          name when it's empty.
        </p>
        <div className="form-actions">
          <button className="btn" type="submit" disabled={save.isPending}>
            Save
          </button>
        </div>
      </form>
      {save.error && <p className="form-error settings-feedback">{save.error.message}</p>}
      {save.isSuccess && !save.isPending && <p className="settings-feedback settings-saved">Saved</p>}
    </section>
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

function TimezoneTile({ settings }: { settings: Settings }) {
  const { timezone } = settings
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
    save.mutate({ ...settings, timezone: draft.trim() })
  }

  function pickDevice() {
    setDraft(deviceZone)
    save.mutate({ ...settings, timezone: deviceZone })
  }

  return (
    <section className="tile span-12 tint-lavender">
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

function DiscordTile({ settings }: { settings: Settings }) {
  const save = useSaveSettings()
  const saveToken = useSaveBotToken()
  const [replacing, setReplacing] = useState(false)

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    save.mutate({
      ...settings,
      discord_webhook_url: form.get('discord_webhook_url') as string,
      discord_mention_user_id: form.get('discord_mention_user_id') as string,
    })
  }

  function submitToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const token = new FormData(event.currentTarget).get('token') as string
    saveToken.mutate(token, { onSuccess: () => setReplacing(false) })
  }

  const tokenForm = !settings.discord_bot_token_set || replacing
  const noKey = !settings.encryption_key_set

  return (
    <section className="tile span-12 tint-blue">
      <h2 className="tile-label">Discord</h2>
      {noKey && (
        <p className="form-error settings-feedback">
          Set <code>ENCRYPTION_KEY</code> on the API (see <code>backend/.env.example</code>) to save a webhook
          URL or bot token. Both are stored encrypted.
        </p>
      )}
      <div className="settings-discord">
        <form className="form" onSubmit={submit}>
          <p className="settings-text">
            Each client gets one reminder at 09:00 on the due date in the timezone above, then every 2 days
            while anything is unpaid. A fee counts as overdue 2 days after its due date.
          </p>
          <label className="field">
            Webhook URL
            <input
              name="discord_webhook_url"
              type="url"
              disabled={noKey}
              defaultValue={settings.discord_webhook_url ?? ''}
              placeholder="https://discord.com/api/webhooks/…"
              spellCheck={false}
              autoComplete="off"
            />
            <small>
              Channel settings › Integrations › Webhooks › New Webhook › Copy Webhook URL. Stored encrypted; empty
              turns reminders off.
            </small>
          </label>
          <label className="field">
            Your Discord user ID
            <input
              name="discord_mention_user_id"
              defaultValue={settings.discord_mention_user_id ?? ''}
              inputMode="numeric"
              pattern="\d{17,20}"
              spellCheck={false}
              autoComplete="off"
            />
            <small>Mentioned in each reminder. Turn on Developer Mode, then right-click your name › Copy User ID.</small>
          </label>
          <div className="form-actions">
            <button className="btn" type="submit" disabled={save.isPending}>
              Save
            </button>
          </div>
          {save.error && <p className="form-error">{save.error.message}</p>}
          {save.isSuccess && !save.isPending && <p className="settings-saved">Saved</p>}
        </form>

        <div className="form">
          <p className="settings-text">
            With a bot token, clients' Discord names and avatars, and yours, sync from Discord every hour. It's
            stored encrypted and never shown again.
          </p>
          {noKey ? null : tokenForm ? (
            <form className="form" onSubmit={submitToken}>
              <label className="field">
                Bot token
                <input name="token" type="password" required spellCheck={false} autoComplete="off" />
                <small>
                  discord.com/developers › New Application › Bot › Reset Token. No intents, permissions or server
                  invite needed.
                </small>
              </label>
              <div className="form-actions">
                <button className="btn" type="submit" disabled={saveToken.isPending}>
                  Save token
                </button>
                {replacing && (
                  <button className="btn secondary" type="button" onClick={() => setReplacing(false)}>
                    Cancel
                  </button>
                )}
              </div>
            </form>
          ) : (
            <div className="settings-token">
              <span className="chip good">Bot token saved</span>
              <button className="link-btn" type="button" onClick={() => setReplacing(true)}>
                Replace
              </button>
              <button
                className="link-btn"
                type="button"
                disabled={saveToken.isPending}
                onClick={() => saveToken.mutate(null)}
              >
                Remove
              </button>
            </div>
          )}
          {saveToken.error && <p className="form-error">{saveToken.error.message}</p>}
        </div>
      </div>
    </section>
  )
}
