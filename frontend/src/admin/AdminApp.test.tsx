import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import AdminApp from './AdminApp'
import { ADMIN_TABS } from './adminTypes'
import { slugify } from './pages'
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

  it('8 табов в конфиге', () => {
    expect(ADMIN_TABS.map((t) => t.id)).toEqual([
      'docs',
      'groups',
      'queue',
      'projects',
      'chat',
      'prompts',
      'graphs',
      'keys',
    ])
  })

  it('slugify: транслит названия в id', () => {
    expect(slugify('Лига студентов')).toBe('liga-studentov')
    expect(slugify('Штаб СО «Тесла»')).toBe('shtab-so-tesla')
    expect(slugify('  Монолит!! ')).toBe('monolit')
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
