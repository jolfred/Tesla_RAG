// Минимальный HTTP-клиент админки: Bearer из того же localStorage,
// ретрай не нужен — при 401 показываем экран входа админа.
import { loadToken } from '../auth/token'

export class AdminApiError extends Error {
  status: number

  constructor(status: number, body: string) {
    super(body || `Request failed with status ${status}`)
    this.name = 'AdminApiError'
    this.status = status
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  headers.set('Content-Type', 'application/json')
  const token = loadToken()
  if (token) {
    headers.set('Authorization', `Bearer ${token}`)
  }
  let resp: Response
  try {
    resp = await fetch(path, { ...init, headers })
  } catch {
    throw new AdminApiError(0, 'Network error')
  }
  if (!resp.ok) {
    throw new AdminApiError(resp.status, await resp.text())
  }
  return (await resp.json()) as T
}

export const adminApi = {
  status: () => req<{ status: string; projects_count: number; jobs_active: number }>('/api/v1/admin/status'),
  projects: () =>
    req<{ projects: { slug: string; name: string; description: string; created_at: string }[] }>(
      '/api/v1/admin/projects',
    ),
}
