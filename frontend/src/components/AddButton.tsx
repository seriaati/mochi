/** A page's main action, adding a record: a plus, named by its label for screen readers and on hover. */
export function AddButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button className="btn page-main add-btn" type="button" aria-label={label} title={label} onClick={onClick}>
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 5v14M5 12h14" />
      </svg>
    </button>
  )
}
