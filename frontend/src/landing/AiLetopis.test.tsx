import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/authContext'
import AiLetopis from './AiLetopis'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const CHAT = {
  answer: 'Штаб отметил 10-летие [https://vk.com/rso_tesla?w=wall-91740386_9511]. Приходи!',
  sources: [{ title: 'Штаб Тесла', url: 'https://vk.com/rso_tesla?w=wall-91740386_9511' }],
  media: ['https://vk.com/photo1.jpg', 'https://vk.com/photo2.jpg'],
  preview: {
    group_name: 'Студенческие отряды КГЭУ «Тесла»',
    published_at: '2025-09-29T12:00:00',
    text: 'Нам 10 лет! Спасибо всем бойцам.',
    photo: 'https://vk.com/photo1.jpg',
    url: 'https://vk.com/rso_tesla?w=wall-91740386_9511',
  },
  mode: 'local',
  facts_count: 2,
  posts_used: 3,
}

describe('AiLetopis: галерея, гиперссылки, VK-превью', () => {
  beforeEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: (query: string) => ({
        matches: false,
        media: query,
        addEventListener: () => undefined,
        removeEventListener: () => undefined,
        addListener: () => undefined,
        removeListener: () => undefined,
      }),
    })
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    )
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      writable: true,
      value: () => null,
    })
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/auth/me') return jsonResponse({ detail: 'no token' }, 401)
      if (url === '/api/v1/auth/guest') {
        return jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })
      }
      if (url === '/api/v1/chat') return jsonResponse(CHAT)
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('фото из media, ссылки-гиперссылки, превью поста', async () => {
    render(
      <AuthProvider>
        <AiLetopis />
      </AuthProvider>,
    )
    fireEvent.change(screen.getByPlaceholderText(/Спроси ИИ Летопись/i), {
      target: { value: 'что такое тесла?' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Спросить/ }))

    // Галерея: главное фото + счётчик + миниатюры
    await waitFor(() => expect(screen.getByAltText('Фото из постов штаба')).toBeTruthy())
    expect(screen.getByText(/1 \/ 2 фото/)).toBeTruthy()

    // Голого URL в тексте нет — вместо него гиперссылка с короткой подписью
    expect(screen.queryByText(/wall-91740386_9511\]\./)).toBeNull()
    const links = screen.getAllByRole('link', { name: /vk\.com/ })
    expect(
      links.some((a) => a.getAttribute('href') === 'https://vk.com/rso_tesla?w=wall-91740386_9511'),
    ).toBe(true)

    // VK-превью справа
    expect(screen.getByLabelText('Предпросмотр поста ВКонтакте')).toBeTruthy()
    expect(screen.getByText('Открыть пост в VK →')).toBeTruthy()
    expect(screen.getByText(/Нам 10 лет/)).toBeTruthy()
  })

  it('без media показывает запасное фото пресет-карточки', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url === '/api/v1/auth/me') return jsonResponse({ detail: 'no token' }, 401)
      if (url === '/api/v1/auth/guest') {
        return jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })
      }
      if (url === '/api/v1/chat') return jsonResponse({ ...CHAT, media: [], preview: null })
      return jsonResponse({ detail: 'not found' }, 404)
    })
    vi.stubGlobal('fetch', fetchMock)
    render(
      <AuthProvider>
        <AiLetopis />
      </AuthProvider>,
    )
    fireEvent.change(screen.getByPlaceholderText(/Спроси ИИ Летопись/i), {
      target: { value: 'вопрос без фото' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Спросить/ }))
    await waitFor(() => expect(screen.getByAltText('Фото из постов штаба')).toBeTruthy())
    // Счётчика и превью нет
    expect(screen.queryByText(/\/ \d+ фото/)).toBeNull()
    expect(screen.queryByLabelText('Предпросмотр поста ВКонтакте')).toBeNull()
  })
})
