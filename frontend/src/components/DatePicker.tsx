import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'
import { formatDay, isoDate, parseDate, todayISO } from '../format.ts'

type Props = {
  /** An ISO date (YYYY-MM-DD), or YYYY-MM with `month`; '' when empty. Omit to leave it uncontrolled. */
  value?: string
  defaultValue?: string
  onChange?: (value: string) => void
  /** Picks a whole month, as YYYY-MM, instead of a day. */
  month?: boolean
  /** The earliest value that can be picked, in the same form as the value. */
  min?: string
  placeholder?: string
  /** Submits the value with the form under this name. */
  name?: string
  required?: boolean
  autoFocus?: boolean
}

const GAP = 6 // px between the field and its calendar
const WIDTH = 304
const MARGIN = 8 // px the calendar keeps from the window's edges
const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const MONTHS = Array.from({ length: 12 }, (_, i) =>
  new Date(2000, i, 1).toLocaleDateString('en-US', { month: 'short' }),
)

function addDays(iso: string, days: number): string {
  const date = parseDate(iso)
  date.setDate(date.getDate() + days)
  return isoDate(date)
}

/** The same day `months` later, or the month's last day when it's shorter. */
function addMonths(iso: string, months: number): string {
  const date = parseDate(iso)
  const first = new Date(date.getFullYear(), date.getMonth() + months, 1)
  const length = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate()
  first.setDate(Math.min(date.getDate(), length))
  return isoDate(first)
}

/** Six whole weeks, Monday first, around the month of `iso`. */
function weeks(iso: string): string[][] {
  const first = `${iso.slice(0, 7)}-01`
  const start = addDays(first, -((parseDate(first).getDay() + 6) % 7))
  return Array.from({ length: 6 }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => addDays(start, w * 7 + d)),
  )
}

/** "October 2026" for an ISO date, or for a YYYY-MM month. */
function monthTitle(iso: string): string {
  const date = parseDate(iso.length === 7 ? `${iso}-01` : iso)
  return date.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })
}

/**
 * A date field with a Bento calendar, in place of the native date and month inputs. Like Select,
 * the calendar is a popover above modal dialogs and focus stays on the field: the arrow keys move
 * the day, Page Up and Down the month (with Shift, the year), Enter picks. Clicking the month's
 * name switches to picking a month, which is all there is with `month`.
 */
export function DatePicker({
  value,
  defaultValue = '',
  onChange,
  month = false,
  min,
  placeholder = month ? 'Pick a month' : 'Pick a date',
  name,
  required,
  autoFocus,
}: Props) {
  const id = useId()
  const field = useRef<HTMLButtonElement>(null)
  const hidden = useRef<HTMLInputElement>(null)
  const menu = useRef<HTMLDivElement>(null)
  const [own, setOwn] = useState(defaultValue)
  const current = value ?? own
  const [open, setOpen] = useState(false)
  const [view, setView] = useState<'days' | 'months'>(month ? 'months' : 'days')
  // The highlighted day, always a whole ISO date, even with `month`.
  const [cursor, setCursor] = useState(todayISO())
  // The first day of the month shown. The keys move it along with the cursor; hovering doesn't,
  // so pointing at a day of the next month doesn't turn the page under the pointer.
  const [page, setPage] = useState(`${todayISO().slice(0, 7)}-01`)
  // Space picks on keyup, through the button's click, so keydown just notes it.
  const spacePressed = useRef(false)
  const days = view === 'days'
  const today = todayISO()
  const minDay = min && min.length === 7 ? `${min}-01` : min
  const tooEarly = (iso: string) => !!minDay && iso < minDay
  const monthTooEarly = (iso: string) => !!minDay && iso.slice(0, 7) < minDay.slice(0, 7)

  // The form can't check `min` on a hidden text input, so say it here.
  useEffect(() => {
    hidden.current?.setCustomValidity(
      current && min && current < min
        ? `Pick ${month ? monthTitle(min) : formatDay(min, { year: true })} or later.`
        : '',
    )
  }, [current, min, month])

  function set(next: string) {
    if (next !== current) {
      setOwn(next)
      onChange?.(next)
    }
  }

  function moveTo(iso: string) {
    const next = minDay && iso < minDay ? minDay : iso
    setCursor(next)
    setPage(`${next.slice(0, 7)}-01`)
  }

  /** Months on from the highlighted day if it's on this page, so a hovered day of the next month isn't counted. */
  function turn(months: number) {
    moveTo(addMonths(cursor.slice(0, 7) === page.slice(0, 7) ? cursor : page, months))
  }

  function show() {
    const button = field.current
    const calendar = menu.current
    if (!button || !calendar) return
    calendar.showPopover()
    // Below the field, or above it when there's more room there; kept inside the window.
    const rect = button.getBoundingClientRect()
    const below = window.innerHeight - rect.bottom - GAP * 2
    const above = rect.top - GAP * 2
    const up = calendar.scrollHeight > below && above > below
    const left = Math.max(MARGIN, Math.min(rect.left, window.innerWidth - WIDTH - MARGIN))
    Object.assign(calendar.style, {
      left: `${left}px`,
      top: up ? '' : `${rect.bottom + GAP}px`,
      bottom: up ? `${window.innerHeight - rect.top + GAP}px` : '',
      maxHeight: `${up ? above : below}px`,
    })
    moveTo(current ? (month ? `${current}-01` : current) : today)
    setView(month ? 'months' : 'days')
    setOpen(true)
  }

  function hide() {
    menu.current?.hidePopover()
    setOpen(false)
  }

  function pickDay(iso: string) {
    if (tooEarly(iso)) return
    set(iso)
    hide()
  }

  function pickMonth(iso: string) {
    if (monthTooEarly(iso)) return
    if (month) {
      set(iso.slice(0, 7))
      hide()
    } else {
      moveTo(iso)
      setView('days')
    }
  }

  function click() {
    if (!open) show()
    else if (spacePressed.current) (days ? pickDay : pickMonth)(cursor)
    else hide()
    spacePressed.current = false
  }

  // Close on a click elsewhere, or when anything scrolls or the window resizes, which would leave
  // the calendar behind. The <label> around the field counts as the field, as in Select.
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
    const row = days ? 7 : 3
    if (key === 'Enter') (days ? pickDay : pickMonth)(cursor)
    else if (key === 'Escape') hide() // preventDefault keeps it from closing the dialog too
    else if (key === 'ArrowLeft') moveTo(days ? addDays(cursor, -1) : addMonths(cursor, -1))
    else if (key === 'ArrowRight') moveTo(days ? addDays(cursor, 1) : addMonths(cursor, 1))
    else if (key === 'ArrowUp') moveTo(days ? addDays(cursor, -row) : addMonths(cursor, -row))
    else if (key === 'ArrowDown') moveTo(days ? addDays(cursor, row) : addMonths(cursor, row))
    else if (key === 'PageUp') turn(days && !event.shiftKey ? -1 : -12)
    else if (key === 'PageDown') turn(days && !event.shiftKey ? 1 : 12)
    else return
    event.preventDefault()
  }

  const step = (by: number) => turn(days ? by : by * 12)
  const year = page.slice(0, 4)
  const label = current ? (month ? monthTitle(current) : formatDay(current, { weekday: true, year: true })) : ''
  const activeId = days ? `${id}-${cursor}` : `${id}-${cursor.slice(0, 7)}`

  return (
    <div className="select">
      <button
        ref={field}
        type="button"
        className="select-field date-field"
        role="combobox"
        aria-haspopup="grid"
        aria-expanded={open}
        aria-controls={`${id}-calendar`}
        aria-activedescendant={open ? activeId : undefined}
        autoFocus={autoFocus}
        onClick={click}
        onKeyDown={keyDown}
      >
        <span className={label ? undefined : 'placeholder'}>{label || placeholder}</span>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <rect x="3.5" y="5" width="17" height="15.5" rx="3" />
          <path d="M3.5 10h17M8 3v4M16 3v4" />
        </svg>
      </button>
      {/* Carries the value into FormData, and into the form's required and min checks. */}
      <input
        ref={hidden}
        className="select-value"
        name={name}
        value={current}
        required={required}
        tabIndex={-1}
        aria-hidden="true"
        onChange={() => {}}
        onFocus={() => field.current?.focus()}
      />
      <div
        ref={menu}
        id={`${id}-calendar`}
        className="select-menu date-menu"
        popover="manual"
        // Keeps focus on the field, and keeps a click in here from reaching the <label> around
        // it, which would reopen the calendar.
        onMouseDown={(event) => event.preventDefault()}
        onClick={(event) => event.preventDefault()}
      >
        <div className="date-head">
          <button
            type="button"
            className="date-title"
            tabIndex={-1}
            aria-pressed={!days}
            disabled={month}
            onClick={() => {
              // Back to days, a month only hovered in the picker doesn't stay highlighted off the page.
              if (!days && cursor.slice(0, 7) !== page.slice(0, 7)) setCursor(page)
              setView(days ? 'months' : 'days')
            }}
          >
            {days ? monthTitle(page) : year}
            {!month && (
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m6 9 6 6 6-6" />
              </svg>
            )}
          </button>
          <button
            type="button"
            className="date-step"
            tabIndex={-1}
            aria-label={days ? 'Previous month' : 'Previous year'}
            onClick={() => step(-1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m15 6-6 6 6 6" />
            </svg>
          </button>
          <button
            type="button"
            className="date-step"
            tabIndex={-1}
            aria-label={days ? 'Next month' : 'Next year'}
            onClick={() => step(1)}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="m9 6 6 6-6 6" />
            </svg>
          </button>
        </div>
        {days ? (
          <div className="date-grid" role="grid" aria-label={monthTitle(page)}>
            <div className="date-row" role="row">
              {WEEKDAYS.map((day) => (
                <span key={day} className="date-weekday" role="columnheader">
                  {day}
                </span>
              ))}
            </div>
            {weeks(page).map((week) => (
              <div key={week[0]} className="date-row" role="row">
                {week.map((iso) => (
                  <button
                    key={iso}
                    id={`${id}-${iso}`}
                    type="button"
                    role="gridcell"
                    tabIndex={-1}
                    className={[
                      'date-day',
                      iso === cursor && 'active',
                      iso === today && 'today',
                      iso.slice(0, 7) !== page.slice(0, 7) && 'outside',
                    ]
                      .filter(Boolean)
                      .join(' ')}
                    aria-label={formatDay(iso, { weekday: true, year: true })}
                    aria-selected={iso === current}
                    disabled={tooEarly(iso)}
                    onPointerMove={() => iso !== cursor && setCursor(iso)}
                    onClick={() => pickDay(iso)}
                  >
                    {parseDate(iso).getDate()}
                  </button>
                ))}
              </div>
            ))}
          </div>
        ) : (
          <div className="date-months" role="grid" aria-label={year}>
            {[0, 3, 6, 9].map((start) => (
              <div key={start} className="date-row" role="row">
                {MONTHS.slice(start, start + 3).map((name, i) => {
                  const iso = addMonths(`${year}-01-01`, start + i)
                  const ym = iso.slice(0, 7)
                  const selected = current.slice(0, 7) === ym
                  return (
                    <button
                      key={name}
                      id={`${id}-${ym}`}
                      type="button"
                      role="gridcell"
                      tabIndex={-1}
                      className={[
                        'date-month',
                        ym === cursor.slice(0, 7) && 'active',
                        ym === today.slice(0, 7) && 'today',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      aria-label={monthTitle(iso)}
                      aria-selected={selected}
                      disabled={monthTooEarly(iso)}
                      onPointerMove={() => ym !== cursor.slice(0, 7) && !monthTooEarly(iso) && setCursor(iso)}
                      onClick={() => pickMonth(iso)}
                    >
                      {name}
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}
        <div className="date-foot">
          <button
            type="button"
            className="link-btn"
            tabIndex={-1}
            disabled={month ? monthTooEarly(today) : tooEarly(today)}
            onClick={() => (month ? pickMonth(today) : pickDay(today))}
          >
            {month ? 'This month' : 'Today'}
          </button>
          {!required && current && (
            <button
              type="button"
              className="link-btn"
              tabIndex={-1}
              onClick={() => {
                set('')
                hide()
              }}
            >
              Clear
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
