import {
  useEffect,
  useId,
  useImperativeHandle,
  useRef,
  useState,
  type MouseEvent,
  type ReactNode,
  type Ref,
  type RefObject,
} from 'react'

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
  // A press that starts inside, e.g. selecting text, and ends on the backdrop shouldn't close it.
  const pressedBackdrop = useRef(false)

  useImperativeHandle(ref, () => ({ close: () => setClosing(true) }), [])

  useEffect(() => {
    const dialog = dialogRef.current
    if (dialog && !dialog.open) dialog.showModal()
  }, [])
  useSwipeToClose(dialogRef, setClosing)

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
      onPointerDown={(event) => {
        pressedBackdrop.current = onBackdrop(event)
      }}
      onClick={(event) => {
        if (pressedBackdrop.current && onBackdrop(event)) setClosing(true)
      }}
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

/** The backdrop targets the dialog too, so tell them apart by where the pointer is. */
function onBackdrop(event: MouseEvent<HTMLDialogElement>) {
  if (event.target !== event.currentTarget) return false
  const rect = event.currentTarget.getBoundingClientRect()
  const { clientX: x, clientY: y } = event
  return x < rect.left || x > rect.right || y < rect.top || y > rect.bottom
}

// Where the dialog is a bottom sheet; matches the phone query in index.css.
const phone = matchMedia('(max-width: 700px)')

/**
 * On phones, dragging the sheet down follows the finger, and letting go far enough down, or with a
 * flick, closes it. It only starts once the sheet is scrolled to the top, so a long form scrolls
 * back up first.
 */
function useSwipeToClose(ref: RefObject<HTMLDialogElement | null>, setClosing: (closing: boolean) => void) {
  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    let start: { y: number; time: number } | null = null
    let offset = 0

    const scrolled = (target: Element) => {
      for (let el: Element | null = target; el && dialog.contains(el); el = el.parentElement) {
        if (el.scrollTop > 0) return true
      }
      return false
    }

    const settle = () => {
      start = null
      dialog.style.transition = 'transform 0.3s var(--ease-out)'
      dialog.style.transform = ''
    }

    const onStart = (event: TouchEvent) => {
      const target = event.target as Element
      const touch = event.touches[0]
      // Not on the backdrop (which targets the dialog too), nor in an open dropdown's menu.
      if (!phone.matches || event.touches.length > 1 || touch.clientY < dialog.getBoundingClientRect().top) return
      if (target.closest('[popover]') || scrolled(target)) return
      start = { y: touch.clientY, time: event.timeStamp }
      offset = 0
    }

    const onMove = (event: TouchEvent) => {
      if (!start) return
      const dy = event.touches[0].clientY - start.y
      // Pulling up scrolls the sheet as usual.
      if (offset === 0 && dy < 0) {
        start = null
        return
      }
      event.preventDefault()
      offset = Math.max(dy, 0)
      dialog.style.transition = 'none'
      dialog.style.transform = `translateY(${offset}px)`
    }

    const onEnd = (event: TouchEvent) => {
      if (!start) return
      const flick = offset > 24 && offset / (event.timeStamp - start.time) > 0.5 // px per ms
      if (offset > dialog.offsetHeight / 4 || flick) {
        start = null
        setClosing(true) // the exit animation carries on from where the finger left it
      } else {
        settle()
      }
    }

    dialog.addEventListener('touchstart', onStart, { passive: true })
    dialog.addEventListener('touchmove', onMove, { passive: false })
    dialog.addEventListener('touchend', onEnd)
    dialog.addEventListener('touchcancel', settle)
    return () => {
      dialog.removeEventListener('touchstart', onStart)
      dialog.removeEventListener('touchmove', onMove)
      dialog.removeEventListener('touchend', onEnd)
      dialog.removeEventListener('touchcancel', settle)
    }
  }, [ref, setClosing])
}
