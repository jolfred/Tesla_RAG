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
  context: {
    graph: '=== ФАКТЫ ===\n- Иван (командир)',
    source_posts: '=== ИСТОЧНИКИ ===\n- текст поста',
    posts: null,
    communities: null,
  },
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

  it('админ: 4 окна с контекстом дословно, пустые — «— пусто —»', async () => {
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
    expect(screen.getByText('Рентген: что получила модель')).toBeTruthy()
    expect(screen.getByText('0. Ответ модели')).toBeTruthy()
    expect(screen.getByText('1. Факты графа')).toBeTruthy()
    expect(screen.getByText('2. Посты-источники')).toBeTruthy()
    expect(screen.getByText('3. Посты и карточки')).toBeTruthy()
    // pretty-print: переносы строк сохранены, не одной строкой
    const pres = document.querySelectorAll('pre')
    expect(pres.length).toBeGreaterThanOrEqual(4)
    expect(pres[1].textContent).toContain('=== ФАКТЫ ===\n- Иван (командир)')
    expect(pres[3].textContent).toBe('— пусто —')
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
    expect(screen.queryByText('Рентген: что получила модель')).toBeNull()
    const chatCalls = fetchMock.mock.calls.filter((c) => String(c[0]) === '/api/v1/chat')
    expect(chatCalls.length).toBeGreaterThan(0)
  })
})
