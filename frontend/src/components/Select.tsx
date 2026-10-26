import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

export type SelectOption<T extends string> = { value: T; label: string; disabled?: boolean }

type Props<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: SelectOption<T>[]
  /** Shown while no option has the value. */
  placeholder?: string
  /** Submits the value with the form under this name. */
  name?: string
  required?: boolean
  /** Names the field when no <label> wraps it. */
  'aria-label'?: string
}

const GAP = 6 // px between the field and its menu
const MAX_HEIGHT = 280

/**
 * A dropdown styled like the other fields, in place of the native <select>. The menu is a
 * popover, so it sits in the top layer above modal dialogs instead of being clipped by them.
 * Focus stays on the field; the arrow keys, Home, End and typing a letter move through options.
 */
export function Select<T extends string>({
  value,
  onChange,
  options,
  placeholder,
  name,
  required,
  'aria-label': ariaLabel,
}: Props<T>) {
  const id = useId()
  const field = useRef<HTMLButtonElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  // Space picks on keyup, through the button's click, so keydown just notes it.
  const spacePressed = useRef(false)
  const selected = options.findIndex((o) => o.value === value)

  function show() {
    const button = field.current
    const list = menu.current
    if (!button || !list) return
    list.showPopover()
    // Below the field, or above it when there's more room there.
    const rect = button.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - GAP * 2
    const above = rect.top - GAP * 2
    const up = list.scrollHeight > below && above > below
    Object.assign(list.style, {
      left: `${rect.left}px`,
      width: `${rect.width}px`,
      top: up ? '' : `${rect.bottom + GAP}px`,
      bottom: up ? `${window.innerHeight - rect.top + GAP}px` : '',
      maxHeight: `${Math.min(MAX_HEIGHT, up ? above : below)}px`,
    })
    setActive(selected)
    setOpen(true)
  }

  function hide() {
    menu.current?.hidePopover()
    setOpen(false)
  }

  function pick(index: number) {
    const option = options[index]
    if (!option || option.disabled) return
    if (option.value !== value) onChange(option.value)
    hide()
  }

  function click() {
    if (!open) show()
    else if (spacePressed.current) pick(active)
    else hide()
    spacePressed.current = false
  }

  // Close on a click elsewhere, or when anything but the menu scrolls or the window resizes,
  // which would leave the menu behind. The <label> around the field counts as the field: its
  // click reaches the button, which closes the menu itself.
  useEffect(() => {
    if (!open) return
    const outside = (event: Event) => {
      const target = event.target as Node
      const own = field.current?.closest('label') ?? field.current
      if (!own?.contains(target) && !menu.current?.contains(target)) hide()
    }
    document.addEventListener('pointerdown', outside)
    document.addEventListener('scroll', outside, true)
    window.addEventListener('resize', hide)
    return () => {
      document.removeEventListener('pointerdown', outside)
      document.removeEventListener('scroll', outside, true)
      window.removeEventListener('resize', hide)
    }
  }, [open])

  useEffect(() => {
    if (open && active >= 0) menu.current?.children[active]?.scrollIntoView({ block: 'nearest' })
  }, [open, active])

  /** The next enabled option from `from`, stepping by `step`; `from` itself when none. */
  function step(from: number, by: number): number {
    for (let i = from + by; i >= 0 && i < options.length; i += by) {
      if (!options[i].disabled) return i
    }
    return from
  }

  function keyDown(event: KeyboardEvent<HTMLButtonElement>) {
    const key = event.key
    if (!open) {
      if (key === 'ArrowDown' || key === 'ArrowUp') {
        event.preventDefault()
        show()
      }
      return
    }
    if (key === 'Tab') return hide()
    if (key === ' ') {
      spacePressed.current = true
      return
    }
    if (key === 'Enter') pick(active) // preventDefault keeps it from clicking the button too
    else if (key === 'Escape') hide() // preventDefault keeps it from closing the dialog too
    else if (key === 'ArrowDown') setActive(step(active, 1))
    else if (key === 'ArrowUp') setActive(step(active, -1))
    else if (key === 'Home') setActive(step(-1, 1))
    else if (key === 'End') setActive(step(options.length, -1))
    else if (key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey) {
      // Jump to the next option starting with the letter typed, wrapping around.
      const letter = key.toLowerCase()
      const order = options.map((_, i) => (active + 1 + i) % options.length)
      const match = order.find(
        (i) => !options[i].disabled && options[i].label.toLowerCase().startsWith(letter),
      )
      if (match !== undefined) setActive(match)
    } else return
    event.preventDefault()
  }

  const current = options[selected]
  return (
    <div className="select">
      <button
        ref={field}
        type="button"
        className="select-field"
        role="combobox"
        aria-label={ariaLabel}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-menu`}
        aria-activedescendant={open && active >= 0 ? `${id}-${active}` : undefined}
        onClick={click}
        onKeyDown={keyDown}
      >
        <span className={current ? undefined : 'placeholder'}>{current?.label ?? placeholder}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>
      {name && (
        // Carries the value into FormData and the form's required check.
        <input
          className="select-value"
          name={name}
          value={value}
          required={required}
          tabIndex={-1}
          aria-hidden="true"
          onChange={() => {}}
          onFocus={() => field.current?.focus()}
        />
      )}
      <div
        ref={menu}
        id={`${id}-menu`}
        className="select-menu"
        popover="manual"
        role="listbox"
        // Keeps focus on the field, and keeps a click in here from reaching the <label> around
        // it, which would reopen the menu.
        onMouseDown={(event) => event.preventDefault()}
        onClick={(event) => event.preventDefault()}
      >
        {options.map((option, index) => (
          <div
            key={option.value}
            id={`${id}-${index}`}
            className={index === active ? 'select-option active' : 'select-option'}
            role="option"
            aria-selected={index === selected}
            aria-disabled={option.disabled || undefined}
            onPointerMove={() => !option.disabled && setActive(index)}
            onClick={() => pick(index)}
          >
            {option.label}
            {index === selected && (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m5 12.5 4.5 4.5L19 7.5" />
              </svg>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
