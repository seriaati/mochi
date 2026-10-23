import { useState, type ComponentProps, type ReactNode } from 'react'

type Props = ComponentProps<'span'> & {
  /** An image such as a synced Discord avatar. */
  src?: string | null
  /** Shown without an image, or when it fails to load: usually initials. */
  fallback: ReactNode
}

/** An avatar in the caller's size and shape (its className), image first, then the fallback. */
export function Avatar({ src, fallback, children, ...props }: Props) {
  const [failed, setFailed] = useState<string>()
  return (
    <span {...props}>
      {src && src !== failed ? (
        <img className="avatar-img" src={src} alt="" loading="lazy" onError={() => setFailed(src)} />
      ) : (
        fallback
      )}
      {children}
    </span>
  )
}
