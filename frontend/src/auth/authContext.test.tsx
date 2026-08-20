import { cleanup, render, screen, waitFor } from '@testing-library/react'
import React from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider, useAuth } from './authContext'
import { loadToken } from './token'

function Probe(): React.JSX.Element {
  const { state } = useAuth()
  return (
    <div>
      <span data-testid="status">{state.status}</span>
      <span data-testid="role">{state.role ?? 'none'}</span>
      <span data-testid="expires">{state.expiresAt ?? 'none'}</span>
    </div>
  )
}

const GUEST_RESPONSE = {
  token: 'guest-token-1',
  role: 'user',
  vk_user_id: null,
  expires_at: '2026-09-19T00:00:00+00:00',
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function mockFetch(routes: Record<string, Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    const route = routes[url]
    if (route) {
      return route
    }
    return jsonResponse({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('authContext', () => {
  beforeEach(() => {
    localStorage.clear()
    delete (window as unknown as { vkBridge?: unknown }).vkBridge
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('bootstrap без токена и без VK -> гость, токен сохранён в localStorage (FR-2.3)', async () => {
    mockFetch({
      '/api/v1/auth/guest': jsonResponse(GUEST_RESPONSE),
    })

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'))
    expect(screen.getByTestId('role').textContent).toBe('user')
    expect(loadToken()).toBe('guest-token-1')
  })

  it('токен в localStorage есть, /me -> 401 -> тихая перевыдача гостя (FR-1.3)', async () => {
    localStorage.setItem('tesla_graphrag_token', 'expired-token')
    mockFetch({
      '/api/v1/auth/me': jsonResponse({ detail: 'expired' }, 401),
      '/api/v1/auth/guest': jsonResponse(GUEST_RESPONSE),
    })

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    await waitFor(() => expect(screen.getByTestId('role').textContent).toBe('user'))
    expect(loadToken()).toBe('guest-token-1')
  })
})