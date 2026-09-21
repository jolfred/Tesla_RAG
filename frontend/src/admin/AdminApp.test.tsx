import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AdminApp from './AdminApp'
import { ADMIN_TABS } from './adminTypes'
import { AuthProvider } from '../auth/authContext'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('AdminApp каркас', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('7 табов в конфиге', () => {
    expect(ADMIN_TABS.map((t) => t.id)).toEqual([
      'docs',
      'groups',
      'projects',
      'chat',
      'prompts',
      'graphs',
      'keys',
    ])
  })

  it('не-админу показывает экран входа', async () => {
    render(
      <AuthProvider>
        <AdminApp />
      </AuthProvider>,
    )
    expect(await screen.findByText(/Вход в админку/)).toBeTruthy()
  })
})
