/** Mochi's mark, as in public/favicon.svg, coloured by the --mark-* tokens to follow the theme. */
export function MochiMark() {
  return (
    <svg className="mochi-mark" viewBox="0 0 100 100" aria-hidden="true">
      <rect width="100" height="100" rx="34" fill="var(--mark-ground)" />
      <ellipse cx="50" cy="74" rx="26.9" ry="3.8" fill="var(--mark-shadow)" />
      <path
        d="M22 64.2C22 43.2 34.9 31 50 31C65.1 31 78 43.2 78 64.2C78 70.9 71.3 73 50 73C28.7 73 22 70.9 22 64.2Z"
        fill="var(--mark-mochi)"
        stroke="var(--mark-outline)"
        strokeWidth="3.5"
      />
      <circle cx="42" cy="54.9" r="2.4" fill="var(--mark-face)" />
      <circle cx="58" cy="54.9" r="2.4" fill="var(--mark-face)" />
      <ellipse cx="34.8" cy="60.4" rx="3.6" ry="2" fill="var(--mark-blush)" />
      <ellipse cx="65.2" cy="60.4" rx="3.6" ry="2" fill="var(--mark-blush)" />
    </svg>
  )
}
