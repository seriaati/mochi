import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { Link, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router'
import { useLogout } from './auth/queries.ts'
import { ClientDetailPage } from './clients/ClientDetailPage.tsx'
import { ClientsPage } from './clients/ClientsPage.tsx'
import { MochiMark } from './components/MochiMark.tsx'
import { androidAppUrl, useInstall } from './install.ts'
import { applyAppUpdate, useAppUpdate, useBackButton, useNotificationPath } from './native.ts'
import { ProjectDetailPage } from './projects/ProjectDetailPage.tsx'
import { MaintenancePage } from './maintenance/MaintenancePage.tsx'
import { OverviewPage } from './overview/OverviewPage.tsx'
import { ProjectsPage } from './projects/ProjectsPage.tsx'
import { syncPush } from './push.ts'
import { SettingsPage } from './settings/SettingsPage.tsx'
import { StatsPage } from './stats/StatsPage.tsx'

const downloadIcon = (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M12 3v12" />
    <path d="m7 10 5 5 5-5" />
    <path d="M5 21h14" />
  </svg>
)

const pages = [
  { path: '/', label: 'Overview' },
  { path: '/projects', label: 'Projects' },
  { path: '/clients', label: 'Clients' },
  { path: '/maintenance', label: 'Retainers' },
  { path: '/stats', label: 'Stats' },
]

/** Where the sliding highlight sits: over the active link, following it on navigation and resize. */
function useNavPill(nav: RefObject<HTMLElement | null>, pathname: string) {
  const [pill, setPill] = useState<CSSProperties | null>(null)

  useLayoutEffect(() => {
    const el = nav.current
    if (!el) return
    const place = () => {
      const active = el.querySelector<HTMLElement>('a.active')
      setPill(
        active && {
          width: active.offsetWidth,
          height: active.offsetHeight,
          transform: `translate(${active.offsetLeft}px, ${active.offsetTop}px)`,
        },
      )
    }
    place()
    const observer = new ResizeObserver(place)
    observer.observe(el)
    return () => observer.disconnect()
  }, [nav, pathname])

  return pill
}

export default function App() {
  const { pathname } = useLocation()
  const nav = useRef<HTMLElement>(null)
  const pill = useNavPill(nav, pathname)
  const logout = useLogout()
  const install = useInstall()
  const appUpdate = useAppUpdate()
  const navigate = useNavigate()

  // The Android app's Back: closes what's open over the page, then follows the history; with none
  // it goes to the Overview, and from there leaves the app.
  useBackButton((canGoBack) => {
    // As Escape does, from the focused element: an open dropdown or calendar closes on its own,
    // and keeps the dialog it's in open.
    const escape = new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })
    const focused = document.activeElement ?? document.body
    focused.dispatchEvent(escape)
    if (escape.defaultPrevented) return true
    // A synthetic Escape doesn't reach a <dialog>: ask it to close, which animates it out
    // (Dialog's onCancel). The last one open is the one on top.
    const dialog = [...document.querySelectorAll('dialog[open]')].at(-1) as HTMLDialogElement | undefined
    if (dialog) {
      if (typeof dialog.requestClose === 'function') dialog.requestClose()
      else dialog.dispatchEvent(new Event('cancel', { cancelable: true })) // before Chrome 134
      return true
    }
    if (canGoBack) navigate(-1)
    else if (pathname !== '/') navigate('/', { replace: true })
    else return false
    return true
  })

  // The Android app's reminders: a tapped one opens its page, and the server gets the app's token
  // again at each start (src/push.ts).
  useNotificationPath((path) => navigate(path))
  useEffect(() => void syncPush(), [])

  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" to="/" aria-label="Mochi: Overview">
          <MochiMark />
          <span>Mochi</span>
        </Link>
        <div className="nav-bar">
          <nav ref={nav} className="nav" aria-label="Main">
            {pill && <span className="nav-pill" style={pill} aria-hidden="true" />}
            {pages.map((page) => (
              <NavLink key={page.path} to={page.path} end={page.path === '/'}>
                {page.label}
              </NavLink>
            ))}
            <NavLink to="/settings" className="nav-icon" aria-label="Settings" title="Settings">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </NavLink>
          </nav>
          <div className="nav-actions">
            {androidAppUrl && (
              <a className="nav-icon nav-button" href={androidAppUrl} aria-label="Get the Android app" title="Get the Android app">
                {downloadIcon}
              </a>
            )}
            {install && (
              <button className="nav-icon nav-button" type="button" aria-label="Install app" title="Install app" onClick={install}>
                {downloadIcon}
              </button>
            )}
            <button
              className="nav-icon nav-button"
              type="button"
              aria-label="Log out"
              title={logout.error ? `Couldn't log out: ${logout.error.message}` : 'Log out'}
              disabled={logout.isPending}
              onClick={() => logout.mutate()}
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <g className="nav-logout-arrow">
                  <path d="m16 17 5-5-5-5" />
                  <path d="M21 12H9" />
                </g>
              </svg>
            </button>
          </div>
        </div>
      </header>
      {appUpdate && (
        <div className="tile tint-blue app-update" role="status">
          <p>A new version of the app is out</p>
          <button className="btn" type="button" onClick={() => applyAppUpdate(appUpdate)}>
            Update
          </button>
        </div>
      )}
      {/* Keyed so each page plays its entrance animation. */}
      <main key={pathname} className="page">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/:id" element={<ClientDetailPage />} />
          <Route path="/maintenance" element={<MaintenancePage />} />
          <Route path="/stats" element={<StatsPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
