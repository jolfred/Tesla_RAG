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
  trace: {
    router: { mode: 'struct' },
    planner: {
      plan: { intent: 'commanders', org_filter: 'Тесла' },
      cypher: 'MATCH (p:Person) RETURN p',
      params: { org: 'Тесла' },
    },
    graph_rows: [{ person: 'Иван' }],
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

  it('админ: окна контекста и трейса дословно, пустые — «— пусто —»', async () => {
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
    expect(screen.getByText('1. Маршрут (выбор режима)')).toBeTruthy()
    expect(screen.getByText('2. План и запрос к графу')).toBeTruthy()
    expect(screen.getByText('3. Выход графа (сырые строки)')).toBeTruthy()
    expect(screen.getByText('4. Факты графа (в модель)')).toBeTruthy()
    // pretty-print: переносы строк и отступы сохранены, не одной строкой
    const pres = document.querySelectorAll('pre')
    expect(pres.length).toBeGreaterThanOrEqual(7)
    const all = [...pres].map((p) => p.textContent ?? '').join('\n')
    expect(all).toContain('режим поиска: struct')
    expect(all).toContain('"intent": "commanders"')
    expect(all).toContain('MATCH (p:Person) RETURN p')
    expect(all).toContain('=== ФАКТЫ ===\n- Иван (командир)')
    expect(all).toContain('— пусто —')
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
