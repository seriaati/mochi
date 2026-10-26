import { useLayoutEffect, useRef, useState, type ComponentProps, type CSSProperties } from 'react'

/**
 * A .segmented group of buttons whose highlight slides to the pressed one (aria-pressed), like
 * the nav pill. It follows the pressed button as it changes and as the group resizes.
 */
export function Segmented({ className, children, ...props }: ComponentProps<'div'>) {
  const group = useRef<HTMLDivElement>(null)
  const [pill, setPill] = useState<CSSProperties | null>(null)

  useLayoutEffect(() => {
    const el = group.current
    if (!el) return
    const place = () => {
      const pressed = el.querySelector<HTMLElement>("button[aria-pressed='true']")
      setPill(
        pressed && {
          width: pressed.offsetWidth,
          height: pressed.offsetHeight,
          transform: `translate(${pressed.offsetLeft}px, ${pressed.offsetTop}px)`,
        },
      )
    }
    place()
    const resized = new ResizeObserver(place)
    resized.observe(el)
    const pressed = new MutationObserver(place)
    pressed.observe(el, { attributeFilter: ['aria-pressed'], subtree: true })
    return () => {
      resized.disconnect()
      pressed.disconnect()
    }
  }, [])

  return (
    <div ref={group} className={className ? `segmented ${className}` : 'segmented'} {...props}>
      {pill && <span className="segmented-pill" style={pill} aria-hidden="true" />}
      {children}
    </div>
  )
}
