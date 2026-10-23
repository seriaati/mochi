/**
 * Typed fetch helper for the FastAPI backend. Paths are relative to /api.
 *
 * VITE_API_URL is the API's origin when it is served elsewhere (e.g. https://api.example.com
 * for a Cloudflare Pages build). Empty means this origin, which in development is the Vite proxy.
 * Requests carry the session cookie either way.
 */

const base = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

type FastApiDetail = string | { msg: string }[] | undefined

async function errorMessage(res: Response): Promise<string> {
  const body = (await res.json().catch(() => ({}))) as { detail?: FastApiDetail }
  if (typeof body.detail === 'string') return body.detail
  if (Array.isArray(body.detail)) return body.detail.map((d) => d.msg).join('. ')
  return `Request failed (${res.status})`
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${base}/api${path}`, {
    method,
    credentials: 'include',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!res.ok) throw new ApiError(res.status, await errorMessage(res))
  return res.status === 204 ? (undefined as T) : ((await res.json()) as T)
}

/** True for the API's answer to a request without a valid session. */
export function isUnauthorized(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  delete: (path: string) => request<void>('DELETE', path),
}
