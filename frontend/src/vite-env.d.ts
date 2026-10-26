interface ImportMetaEnv {
  /** The API's origin, e.g. https://api.example.com. Empty: same origin (the dev proxy). */
  readonly VITE_API_URL?: string
  /** The public demo's password, shown and filled in on the login screen. Unset elsewhere. */
  readonly VITE_DEMO_PASSWORD?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
