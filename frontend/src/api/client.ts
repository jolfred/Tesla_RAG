import type {
  AdminRequest,
  AuthResponse,
  ChatRequest,
  ChatResponse,
  LogoutResponse,
  MeResponse,
  StatusResponse,
  VkRequest,
  WikiNode,
  WikiPageData,
} from '../types'

export class ApiError extends Error {
  status: number

  constructor(status: number, body: string) {
    super(body || `Request failed with status ${status}`)
    this.name = 'ApiError'
    this.status = status
  }
}

/**
 * Fetch-обёртка с Bearer-инжекцией (FR-2.3) и тихой перевыдачей токена при 401 (FR-1.3).
 * Переиспользуется в M2/M3 (NFR-5).
 */
export class ApiClient {
  token: string | null = null
  refresh: (() => Promise<void>) | null = null

  setToken(token: string | null): void {
    this.token = token
  }

  setRefresh(refresh: (() => Promise<void>) | null): void {
    this.refresh = refresh
  }

  private async request<T>(path: string, init: RequestInit = {}, retried = false): Promise<T> {
    const headers = new Headers(init.headers)
    headers.set('Content-Type', 'application/json')
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`)
    }

    let resp: Response
    try {
      resp = await fetch(path, { ...init, headers })
    } catch {
      throw new ApiError(0, 'Network error')
    }

    // 401 на не-auth-эндпоинте -> тихая перевыдача гостевого токена и ретрай (FR-1.3)
    if (resp.status === 401 && !retried && !path.startsWith('/api/v1/auth/') && this.refresh) {
      await this.refresh()
      return this.request<T>(path, init, true)
    }

    if (!resp.ok) {
      throw new ApiError(resp.status, await resp.text())
    }
    return (await resp.json()) as T
  }

  guest(): Promise<AuthResponse> {
    return this.request<AuthResponse>('/api/v1/auth/guest', { method: 'POST' })
  }

  admin(body: AdminRequest): Promise<AuthResponse> {
    return this.request<AuthResponse>('/api/v1/auth/admin', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  vk(body: VkRequest): Promise<AuthResponse> {
    return this.request<AuthResponse>('/api/v1/auth/vk', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  me(): Promise<MeResponse> {
    return this.request<MeResponse>('/api/v1/auth/me')
  }

  logout(): Promise<LogoutResponse> {
    return this.request<LogoutResponse>('/api/v1/auth/logout', { method: 'POST' })
  }

  chat(body: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/api/v1/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    })
  }

  status(): Promise<StatusResponse> {
    return this.request<StatusResponse>('/api/v1/status')
  }

  wikiPages(): Promise<{ pages: WikiNode[] }> {
    return this.request<{ pages: WikiNode[] }>('/api/v1/wiki/pages')
  }

  wikiPage(slug: string): Promise<WikiPageData> {
    return this.request<WikiPageData>(`/api/v1/wiki/page?slug=${encodeURIComponent(slug)}`)
  }
}

export const api = new ApiClient()