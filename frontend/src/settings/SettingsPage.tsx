import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from 'react'
import { useLocation } from 'react-router'
import { Select } from '../components/Select.tsx'
import { formatDay, plural } from '../format.ts'
import { applyTheme, savedTheme, type Theme } from '../theme.ts'
import {
  useChooseKeniDestination,
  useConnectKeni,
  useFindKeniOptions,
  useKeni,
  useKeniOptions,
  useSaveBotToken,
  useSaveSettings,
  useSettings,
  type Keni,
  type KeniDestination,
  type KeniOptions,
  type Settings,
} from './queries.ts'
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
  const { hash } = useLocation()
  const loaded = settings.data !== undefined

  // Links such as /settings#discord land on their tile once it renders.
  useEffect(() => {
    if (loaded && hash) document.getElementById(hash.slice(1))?.scrollIntoView({ block: 'start' })
  }, [loaded, hash])

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
          <KeniTile settings={settings.data} />
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
    <section id="discord" className="tile span-12 tint-blue">
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

/** The hosted Keni, filled in for a first connection. */
const KENI_URL = 'https://app.keni.seria.moe'

function KeniTile({ settings }: { settings: Settings }) {
  const keni = useKeni()
  const noKey = !settings.encryption_key_set

  return (
    <section className="tile span-12 tint-blue">
      <h2 className="tile-label">Keni</h2>
      {noKey && !keni.data?.url && (
        <p className="form-error settings-feedback">
          Set <code>ENCRYPTION_KEY</code> on the API (see <code>backend/.env.example</code>) to connect Keni. The API
          key is stored encrypted.
        </p>
      )}
      <div className="settings-discord">
        <div>
          <p className="settings-text">
            Records the money you receive as income in the Keni wallet and category you choose: project and addition
            payments, recorded maintenance payments, and auto transfers once they&rsquo;re due. Edits and deletes here
            follow it there.
          </p>
          <p className="settings-text">
            Money received before you connect stays out of Keni. Amounts are sent as NT$, whatever the
            wallet&rsquo;s currency.
          </p>
        </div>
        {keni.isPending && <p className="settings-text">Loading…</p>}
        {keni.error && (
          <p className="form-error">Couldn&rsquo;t load the Keni connection: {keni.error.message}</p>
        )}
        {keni.data && (keni.data.url ? <KeniStatus keni={keni.data} /> : <KeniConnect disabled={noKey} />)}
      </div>
    </section>
  )
}

/** Wallet and category pickers, filled from the Keni account. */
function KeniDestinationFields({
  options,
  value,
  onChange,
}: {
  options: KeniOptions
  value: KeniDestination
  onChange: (value: KeniDestination) => void
}) {
  return (
    <>
      <label className="field">
        Wallet
        <Select
          value={value.wallet_id}
          onChange={(wallet_id) => onChange({ ...value, wallet_id })}
          placeholder="Choose a wallet"
          options={options.wallets.map((w) => ({ value: w.id, label: `${w.name} (${w.currency})` }))}
        />
      </label>
      <label className="field">
        Category
        <Select
          value={value.category_id}
          onChange={(category_id) => onChange({ ...value, category_id })}
          placeholder="Choose a category"
          options={options.categories.map((c) => ({ value: c.id, label: c.name }))}
        />
      </label>
    </>
  )
}

function KeniConnect({ disabled }: { disabled: boolean }) {
  const find = useFindKeniOptions()
  const connect = useConnectKeni()
  const [destination, setDestination] = useState<KeniDestination>({ wallet_id: '', category_id: '' })
  const options = find.data
  const login = find.variables

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    find.mutate(
      { url: form.get('url') as string, token: form.get('token') as string },
      {
        onSuccess: (found) =>
          setDestination({
            wallet_id: found.wallets[0]?.id ?? '',
            // A category named Freelance is the likely pick; otherwise the user chooses.
            category_id: found.categories.find((c) => c.name.toLowerCase() === 'freelance')?.id ?? '',
          }),
      },
    )
  }

  /** A changed URL or key needs its wallets and categories found again. */
  function edited() {
    find.reset()
    connect.reset()
  }

  return (
    <form className="form" onSubmit={submit}>
      <label className="field">
        Keni URL
        <input
          name="url"
          type="url"
          required
          disabled={disabled}
          defaultValue={KENI_URL}
          onChange={edited}
          spellCheck={false}
          autoComplete="off"
        />
        <small>The hosted app, or your own Keni.</small>
      </label>
      <label className="field">
        API key
        <input
          name="token"
          type="password"
          required
          disabled={disabled}
          onChange={edited}
          spellCheck={false}
          autoComplete="off"
        />
        <small>In Keni: Settings › API tokens. Stored encrypted and never shown again.</small>
      </label>
      {options?.wallets.length && login ? (
        <>
          <KeniDestinationFields options={options} value={destination} onChange={setDestination} />
          <div className="form-actions">
            <button
              className="btn"
              type="button"
              disabled={connect.isPending || !destination.wallet_id || !destination.category_id}
              onClick={() => connect.mutate({ ...login, ...destination })}
            >
              Connect
            </button>
          </div>
        </>
      ) : (
        <>
          {options && <p className="settings-text">No wallets in this Keni account yet. Add one in Keni first.</p>}
          <div className="form-actions">
            <button className="btn" type="submit" disabled={disabled || find.isPending}>
              Load from Keni
            </button>
          </div>
        </>
      )}
      {find.error && <p className="form-error">{find.error.message}</p>}
      {connect.error && <p className="form-error">{connect.error.message}</p>}
    </form>
  )
}

function KeniStatus({ keni }: { keni: Keni }) {
  const disconnect = useConnectKeni()
  const [confirming, setConfirming] = useState(false)

  return (
    <div className="form">
      <div className="settings-token">
        {keni.error ? <span className="chip warn">Sync stopped</span> : <span className="chip good">Connected</span>}
      </div>
      <p className="settings-text">
        Recording in <b>{keni.wallet_name}</b> ({keni.wallet_currency}) as <b>{keni.category_name}</b> on{' '}
        {new URL(keni.url!).host} since {formatDay(keni.connected_on!, { year: true })}.
      </p>
      {keni.error ? (
        <p className="form-error">
          {keni.error}. It retries every minute
          {keni.pending > 0 && `, with ${plural(keni.pending, 'change')} waiting`}.
        </p>
      ) : keni.pending > 0 ? (
        <p className="settings-text">{plural(keni.pending, 'change')} waiting to send. Keni syncs every minute.</p>
      ) : (
        <p className="settings-saved">Everything is in Keni</p>
      )}
      <KeniChangeDestination keni={keni} />
      <div className="form-actions">
        <button
          className="btn danger"
          type="button"
          disabled={disconnect.isPending}
          onClick={() => (confirming ? disconnect.mutate(null) : setConfirming(true))}
        >
          {confirming ? 'Confirm disconnect' : 'Disconnect'}
        </button>
      </div>
      {confirming && !disconnect.error && (
        <p className="settings-text">
          What&rsquo;s in Keni stays there, but changes here stop following it. Connecting again starts afresh.
        </p>
      )}
      {disconnect.error && <p className="form-error">{disconnect.error.message}</p>}
    </div>
  )
}

function KeniChangeDestination({ keni }: { keni: Keni }) {
  const options = useKeniOptions()
  const choose = useChooseKeniDestination()
  const saved = { wallet_id: keni.wallet_id!, category_id: keni.category_id! }
  const [destination, setDestination] = useState<KeniDestination>(saved)
  const changed = destination.wallet_id !== saved.wallet_id || destination.category_id !== saved.category_id

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    choose.mutate(destination)
  }

  if (options.isPending) return <p className="settings-text">Loading wallets and categories…</p>
  if (options.error)
    return <p className="form-error">Couldn&rsquo;t load wallets and categories: {options.error.message}</p>
  return (
    <form className="form" onSubmit={submit}>
      <KeniDestinationFields options={options.data} value={destination} onChange={setDestination} />
      <p className="settings-text">
        A new wallet or category applies to income sent from then on. What&rsquo;s already in Keni stays where it is.
      </p>
      <div className="form-actions">
        <button className="btn" type="submit" disabled={!changed || choose.isPending}>
          Save
        </button>
      </div>
      {choose.error && <p className="form-error">{choose.error.message}</p>}
      {choose.isSuccess && !choose.isPending && !changed && <p className="settings-saved">Saved</p>}
    </form>
  )
}
