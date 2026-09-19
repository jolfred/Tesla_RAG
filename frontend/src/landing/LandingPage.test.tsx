import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { AuthProvider } from '../auth/authContext'
import LandingPage from './LandingPage'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('LandingPage гид-web', () => {
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
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })))
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe(): void {}
        unobserve(): void {}
        disconnect(): void {}
      },
    )
    // WebGL отсутствует в jsdom — компонент должен деградировать тихо
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
      writable: true,
      value: () => null,
    })
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('рендерит hero, летопись, marquee и CTA', () => {
    render(
      <AuthProvider>
        <LandingPage />
      </AuthProvider>,
    )
    expect(screen.getByText(/Твоё самое незабываемое/i)).toBeTruthy()
    expect(screen.getByPlaceholderText(/Спроси ИИ Летопись/i)).toBeTruthy()
    expect(screen.getByText(/Ограниченный набор 2026 активен/i)).toBeTruthy()
    expect(screen.getByText(/Подать заявку в отряд/i)).toBeTruthy()
    expect(screen.getByText(/Сколько заработаю/i)).toBeTruthy()
    // Marquee содержит отряды (дублированный ряд) + настоящие логотипы в единых рамках
    expect(screen.getAllByText(/Исида/i).length).toBeGreaterThanOrEqual(1)
    const logos = document.querySelectorAll('section[aria-label="Лента отрядов"] img[alt^="Логотип"]')
    expect(logos.length).toBeGreaterThanOrEqual(9)
    logos.forEach((img) => {
      expect(img.getAttribute('width')).toBe('44')
      expect(img.getAttribute('height')).toBe('44')
    })
    // Хедер: логотип Теслы крупный (80px)
    const headerLogo = screen.getByAltText('Логотип штаба Тесла')
    expect(headerLogo.getAttribute('width')).toBe('80')
    // Футер: слоган справа + отряды по направлениям со ссылками
    expect(screen.getByText(/Только Тесла — только Победа/)).toBeTruthy()
    const footer = document.querySelector('footer')
    expect(footer).toBeTruthy()
    const isidaLinks = [...(footer as HTMLElement).querySelectorAll('a')].filter(
      (a) => a.getAttribute('href') === 'https://vk.ru/sso_isida',
    )
    expect(isidaLinks.length).toBeGreaterThanOrEqual(1)
    // Направление есть и в секции направлений, и в футере
    expect(screen.getAllByText('Строительное').length).toBeGreaterThanOrEqual(2)
  })
})
