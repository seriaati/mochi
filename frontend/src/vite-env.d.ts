interface ImportMetaEnv {
  /** The API's origin, e.g. https://api.example.com. Empty: same origin (the dev proxy). */
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
