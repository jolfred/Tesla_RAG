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

export interface AdminGroup {
  url: string
  domain: string
  enabled: boolean
  posts_count: number
  posts_mtime: number
  meta_name: string
  projects: string[]
}

export interface AdminJob {
  id: string
  kind: string
  project_slug: string
  status: string
  log_path: string
  error: string
  created_at: string
  finished_at: string
  log_tail?: string
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
  indexProject: (slug: string, body: { model: string; extractor: string; min_date: string; force: boolean }) =>
    req<{ job_id: string; status: string }>(`/api/v1/admin/projects/${encodeURIComponent(slug)}/index`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  projectStats: (slug: string) =>
    req<{
      source_model: string
      collection: string
      neo4j_nodes: number
      neo4j_relations: number
      qdrant_points: number
      error: string
    }>(`/api/v1/admin/projects/${encodeURIComponent(slug)}/stats`),
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
  groups: () => req<{ groups: AdminGroup[] }>('/api/v1/admin/groups'),
  addGroup: (url: string) =>
    req<AdminGroup>('/api/v1/admin/groups', { method: 'POST', body: JSON.stringify({ url }) }),
  scrapeGroup: (domain: string, meta_only: boolean) =>
    req<{ job_id: string; status: string }>(`/api/v1/admin/groups/${encodeURIComponent(domain)}/scrape`, {
      method: 'POST',
      body: JSON.stringify({ meta_only }),
    }),
  jobs: () => req<{ jobs: AdminJob[] }>('/api/v1/admin/jobs'),
  job: (id: string) => req<AdminJob>(`/api/v1/admin/jobs/${encodeURIComponent(id)}`),
  adminChat: (question: string, project_slug: string) =>
    req<{
      answer: string
      sources: { title: string; url: string }[]
      mode: string
      facts_count: number
      posts_used: number
      calls: { title: string; text: string }[] | null
      trace_id: string | null
    }>('/api/v1/admin/chat', { method: 'POST', body: JSON.stringify({ question, project_slug }) }),
  prompts: () =>
    req<{
      prompts: { key: string; title: string; text: string; custom: boolean; updated_at: string }[]
    }>('/api/v1/admin/prompts'),
  setPrompt: (key: string, text: string) =>
    req<{ ok: boolean }>(`/api/v1/admin/prompts/${encodeURIComponent(key)}`, {
      method: 'PUT',
      body: JSON.stringify({ text }),
    }),
  resetPrompt: (key: string) =>
    req<{ ok: boolean; text: string }>(`/api/v1/admin/prompts/${encodeURIComponent(key)}/reset`, {
      method: 'POST',
    }),
  graphExport: (project_slug: string) =>
    req<{
      source_model: string
      browser_url: string
      nodes: { id: string; label: string; name: string }[]
      edges: { a: string; rel: string; b: string }[]
    }>(`/api/v1/admin/graph/export?project_slug=${encodeURIComponent(project_slug)}`),
}
