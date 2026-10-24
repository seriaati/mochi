import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type RefObject } from 'react'
import { Link, NavLink, Route, Routes, useLocation } from 'react-router'
import { ClientDetailPage } from './clients/ClientDetailPage.tsx'
import { ClientsPage } from './clients/ClientsPage.tsx'
import { useFavicon } from './favicon.ts'
import { ProjectDetailPage } from './projects/ProjectDetailPage.tsx'
import { MaintenancePage } from './maintenance/MaintenancePage.tsx'
import { OverviewPage } from './overview/OverviewPage.tsx'
import { ProjectsPage } from './projects/ProjectsPage.tsx'
import { useSettings } from './settings/queries.ts'
import { SettingsPage } from './settings/SettingsPage.tsx'

const pages = [
  { path: '/', label: 'Overview' },
  { path: '/projects', label: 'Projects' },
  { path: '/clients', label: 'Clients' },
  { path: '/maintenance', label: 'Maintenance' },
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
  const settings = useSettings()
  const studio = settings.data?.studio_name ?? 'Studio'
  const logo = settings.data?.studio_logo

  useEffect(() => {
    document.title = studio
  }, [studio])
  useFavicon(logo)

  return (
    <div className="shell">
      <header className="topbar">
        {/* Empty until settings load, so the default name doesn't flash first. */}
        <Link className="brand" to="/" aria-label={`${studio}: Overview`}>
          {!settings.isPending && (
            <>
              {logo ? <img className="brand-logo" src={logo} alt="" /> : <i />}
              <span>{studio}</span>
            </>
          )}
        </Link>
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
      </header>
      {/* Keyed so each page plays its entrance animation. */}
      <main key={pathname} className="page">
        <Routes>
          <Route path="/" element={<OverviewPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:id" element={<ProjectDetailPage />} />
          <Route path="/clients" element={<ClientsPage />} />
          <Route path="/clients/:id" element={<ClientDetailPage />} />
          <Route path="/maintenance" element={<MaintenancePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
