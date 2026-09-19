import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/authContext'
import AiLetopis from './AiLetopis'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function previews(n: number): object[] {
  return Array.from({ length: n }, (_, i) => ({
    group_name: `Отряд ${i + 1}`,
    published_at: `2025-0${i + 1}-01T12:00:00`,
    text: `Текст поста ${i + 1} про целину и отряды.`,
    photo: `https://vk.com/photo${i + 1}.jpg`,
    url: `https://vk.com/wall${i + 1}`,
  }))
}

const CHAT = {
  answer: 'Штаб отметил 10-летие [https://vk.com/rso_tesla?w=wall-91740386_9511]. Приходи!',
  sources: [{ title: 'Штаб Тесла', url: 'https://vk.com/rso_tesla?w=wall-91740386_9511' }],
  media: ['https://vk.com/photo1.jpg'],
  previews: previews(3),
  mode: 'local',
  facts_count: 2,
  posts_used: 3,
}

function mockChat(chat: object): void {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url === '/api/v1/auth/me') return jsonResponse({ detail: 'no token' }, 401)
    if (url === '/api/v1/auth/guest') {
      return jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })
    }
    if (url === '/api/v1/chat') return jsonResponse(chat)
    return jsonResponse({ detail: 'not found' }, 404)
  })
  vi.stubGlobal('fetch', fetchMock)
}

describe('AiLetopis: карусель превью, гиперссылки', () => {
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
    mockChat(CHAT)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  async function askQuestion(q = 'что такое тесла?'): Promise<void> {
    render(
      <AuthProvider>
        <AiLetopis />
      </AuthProvider>,
    )
    fireEvent.change(screen.getByPlaceholderText(/Спроси ИИ Летопись/i), {
      target: { value: q },
    })
    fireEvent.click(screen.getByRole('button', { name: /Спросить/ }))
    await waitFor(() => expect(screen.getByLabelText('Предпросмотр поста ВКонтакте')).toBeTruthy())
  }

  it('карусель превью со стрелками, без галереи и ссылок-источников', async () => {
    await askQuestion()
    // Счётчик и первое превью
    expect(screen.getByText('Пост 1 / 3')).toBeTruthy()
    expect(screen.getByText(/Текст поста 1/)).toBeTruthy()
    // Стрелка вперёд листает
    fireEvent.click(screen.getByRole('button', { name: 'Следующий пост' }))
    expect(screen.getByText('Пост 2 / 3')).toBeTruthy()
    expect(screen.getByText(/Текст поста 2/)).toBeTruthy()
    // Назад — циклически
    fireEvent.click(screen.getByRole('button', { name: 'Предыдущий пост' }))
    fireEvent.click(screen.getByRole('button', { name: 'Предыдущий пост' }))
    expect(screen.getByText('Пост 3 / 3')).toBeTruthy()

    // Галереи фото нет
    expect(screen.queryByAltText('Фото из постов штаба')).toBeNull()
    // Ссылок-источников в конце нет
    expect(screen.queryByText(/^↗/)).toBeNull()

    // Голого URL в тексте нет — вместо него гиперссылка с короткой подписью
    expect(screen.queryByText(/wall-91740386_9511\]\./)).toBeNull()
    const links = screen.getAllByRole('link', { name: /vk\.com/ })
    expect(
      links.some((a) => a.getAttribute('href') === 'https://vk.com/rso_tesla?w=wall-91740386_9511'),
    ).toBe(true)
  })

  it('без превью карусели нет', async () => {
    cleanup()
    mockChat({ ...CHAT, previews: [] })
    render(
      <AuthProvider>
        <AiLetopis />
      </AuthProvider>,
    )
    fireEvent.change(screen.getByPlaceholderText(/Спроси ИИ Летопись/i), {
      target: { value: 'вопрос без превью' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Спросить/ }))
    await waitFor(() => expect(screen.getByText('ВЫДЕРЖКА ИЗ БАЗЫ ШТАБА')).toBeTruthy())
    expect(screen.queryByLabelText('Предпросмотр поста ВКонтакте')).toBeNull()
    expect(screen.queryByText(/Пост 1 \//)).toBeNull()
  })
})
