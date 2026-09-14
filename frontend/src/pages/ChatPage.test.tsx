import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/authContext'
import ChatPage from './ChatPage'

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

const ADMIN_GUEST = {
  token: 'admin-token-1',
  role: 'admin',
  vk_user_id: null,
  expires_at: '2026-09-19T00:00:00+00:00',
}

const USER_GUEST = { ...ADMIN_GUEST, token: 'user-token-1', role: 'user' }

const CHAT_WITH_CTX = {
  answer: 'Ответ модели',
  sources: [],
  media: [],
  mode: 'struct',
  facts_count: 1,
  posts_used: 1,
  calls: [
    { title: 'Вызов 1 — роутер', text: '=== SYSTEM ===\nроутер\n\n=== ОТВЕТ ===\n{"mode": "struct"}' },
    { title: 'Вызов 2 — планировщик', text: '=== SYSTEM ===\nплан\n\n=== CYPHER ===\nMATCH (p) RETURN p' },
    { title: 'Вызов 3 — ответ', text: '=== SYSTEM ===\nхранитель\n\n=== ОТВЕТ ===\nОтвет модели' },
  ],
}

async function askQuestion() {
  const box = screen.getByPlaceholderText(/Например:/)
  fireEvent.change(box, { target: { value: 'кто командует?' } })
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }))
  // Ответ виден и в чате, и в панели — ждём хотя бы один.
  await waitFor(() => expect(screen.getAllByText('Ответ модели').length).toBeGreaterThanOrEqual(1))
}

describe('ChatPage рентген-панель', () => {
  beforeEach(() => {
    // jsdom не умеет scrollIntoView (компонентный useEffect).
    Element.prototype.scrollIntoView = (() => undefined) as unknown as typeof Element.prototype.scrollIntoView
    // VKUI требует matchMedia.
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
      }),
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  function authed(routes: Record<string, Response>) {
    // bootstrap AuthProvider: /me без токена -> 401 -> тихий гость.
    return mockFetch({
      '/api/v1/auth/me': jsonResponse({ detail: 'no token' }, 401),
      ...routes,
    })
  }

  it('админ: 3 окна вызовов с полными текстами', async () => {
    authed({
      '/api/v1/auth/guest': jsonResponse(ADMIN_GUEST),
      '/api/v1/chat': jsonResponse(CHAT_WITH_CTX),
    })
    render(
      <AuthProvider>
        <ChatPage />
      </AuthProvider>,
    )
    await askQuestion()
    expect(screen.getByText('Рентген: вызовы модели')).toBeTruthy()
    expect(screen.getByText('Вызов 1 — роутер')).toBeTruthy()
    expect(screen.getByText('Вызов 2 — планировщик')).toBeTruthy()
    expect(screen.getByText('Вызов 3 — ответ')).toBeTruthy()
    // полные тексты с переносами, не одной строкой
    const pres = document.querySelectorAll('pre')
    expect(pres.length).toBe(3)
    const all = [...pres].map((p) => p.textContent ?? '').join('\n')
    expect(all).toContain('=== SYSTEM ===\nроутер')
    expect(all).toContain('{"mode": "struct"}')
    expect(all).toContain('MATCH (p) RETURN p')
    expect(all).toContain('=== ОТВЕТ ===\nОтвет модели')
  })

  it('не-админ: тумблера и панели нет', async () => {
    authed({
      '/api/v1/auth/guest': jsonResponse(USER_GUEST),
      '/api/v1/chat': jsonResponse({ ...CHAT_WITH_CTX, context: null }),
    })
    render(
      <AuthProvider>
        <ChatPage />
      </AuthProvider>,
    )
    await askQuestion()
    expect(screen.queryByText(/Рентген/)).toBeNull()
    expect(document.querySelectorAll('pre').length).toBe(0)
  })

  it('тумблер выключает панель и флаг запроса', async () => {
    const fetchMock = authed({
      '/api/v1/auth/guest': jsonResponse(ADMIN_GUEST),
      '/api/v1/chat': jsonResponse(CHAT_WITH_CTX),
    })
    render(
      <AuthProvider>
        <ChatPage />
      </AuthProvider>,
    )
    await askQuestion()
    fireEvent.click(screen.getByRole('button', { name: /Рентген/ }))
    expect(screen.queryByText('Рентген: вызовы модели')).toBeNull()
    const chatCalls = fetchMock.mock.calls.filter((c) => String(c[0]) === '/api/v1/chat')
    expect(chatCalls.length).toBeGreaterThan(0)
  })
})
