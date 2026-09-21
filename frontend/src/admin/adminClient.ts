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

export interface AdminDocument {
  doc_id: string
  filename: string
  title: string
  size: number
  projects: string[]
}

export interface AdminProjectDetail {
  slug: string
  name: string
  description: string
  created_at: string
  items: { item_type: string; item_id: string }[]
}

export const adminApi = {
  status: () => req<{ status: string; projects_count: number; jobs_active: number }>('/api/v1/admin/status'),
  projects: () =>
    req<{ projects: { slug: string; name: string; description: string; created_at: string }[] }>(
      '/api/v1/admin/projects',
    ),
  createProject: (body: { slug: string; name: string; description: string }) =>
    req<{ slug: string; name: string; description: string }>('/api/v1/admin/projects', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  projectDetail: (slug: string) =>
    req<AdminProjectDetail>(`/api/v1/admin/projects/${encodeURIComponent(slug)}`),
  deleteProject: (slug: string) =>
    req<{ ok: boolean }>(`/api/v1/admin/projects/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
  attachItem: (slug: string, item_type: string, item_id: string) =>
    req<{ ok: boolean }>(`/api/v1/admin/projects/${encodeURIComponent(slug)}/items`, {
      method: 'POST',
      body: JSON.stringify({ item_type, item_id }),
    }),
  detachItem: (slug: string, item_type: string, item_id: string) =>
    req<{ ok: boolean }>(
      `/api/v1/admin/projects/${encodeURIComponent(slug)}/items?item_type=${encodeURIComponent(item_type)}&item_id=${encodeURIComponent(item_id)}`,
      { method: 'DELETE' },
    ),
  documents: () => req<{ documents: AdminDocument[] }>('/api/v1/admin/documents'),
  uploadDocument: async (file: File, title: string): Promise<{ doc_id: string; title: string }> => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('title', title)
    const headers = new Headers()
    const token = loadToken()
    if (token) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    let resp: Response
    try {
      resp = await fetch('/api/v1/admin/documents/upload', { method: 'POST', headers, body: fd })
    } catch {
      throw new AdminApiError(0, 'Network error')
    }
    if (!resp.ok) {
      throw new AdminApiError(resp.status, await resp.text())
    }
    return (await resp.json()) as { doc_id: string; title: string }
  },
}
