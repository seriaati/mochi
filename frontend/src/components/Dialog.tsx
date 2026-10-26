import { useEffect, useId, useImperativeHandle, useRef, useState, type ReactNode, type Ref } from 'react'

/** Closes the dialog with its exit animation, then calls onClose. */
export type DialogHandle = { close: () => void }

type Props = { title: string; onClose: () => void; children: ReactNode; ref?: Ref<DialogHandle> }

/**
 * A modal native <dialog>: render it to open. Close it through its ref (or Escape) to animate out
 * before onClose; stopping rendering it closes it at once.
 */
export function Dialog({ title, onClose, children, ref }: Props) {
  const dialogRef = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [closing, setClosing] = useState(false)

  useImperativeHandle(ref, () => ({ close: () => setClosing(true) }), [])

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])

  return (
    <dialog
      ref={dialogRef}
      className={closing ? 'dialog closing' : 'dialog'}
      aria-labelledby={titleId}
      // Escape animates out too; when the browser won't let it be held, the dialog closes at once.
      onCancel={(event) => {
        event.preventDefault()
        setClosing(true)
      }}
      onClose={onClose}
      onAnimationEnd={(event) => {
        // sheet-out on phones, where the dialog is a bottom sheet.
        if (event.animationName === 'dialog-out' || event.animationName === 'sheet-out') onClose()
      }}
    >
      <h2 id={titleId}>{title}</h2>
      {children}
    </dialog>
  )
}
