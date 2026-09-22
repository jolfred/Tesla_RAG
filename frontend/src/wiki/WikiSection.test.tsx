import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WikiSection from './WikiSection'

const PAGES = {
  pages: [
    { slug: 'lso/spo_yunost', title: 'СПО «Юность»', kind: 'squad' },
    { slug: 'persons/bogachev_egor', title: 'Богачёв Егор', kind: 'person' },
    { slug: 'hq/index', title: 'Штаб СО КГЭУ «Тесла»', kind: 'hq' },
  ],
}
const ARTICLE = {
  status: 'success',
  slug: 'lso/spo_yunost',
  markdown:
    '# СПО «Юность»\n\nКомандир — [[persons/bogachev_egor|Богачёв Егор]] ' +
    '(Источник: ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)), опубл. 2021-04-07).\n' +
    '\n## Источники данных\n\n- `../posts/posts_spoyunost2020.jsonl`\n',
  links: ['persons/bogachev_egor'],
  sources: ['https://vk.com/spoyunost2020?w=wall-198864697_133'],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('WikiSection', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/api/v1/wiki/pages')) return jsonResponse(PAGES)
        if (url.includes('/api/v1/wiki/page')) return jsonResponse(ARTICLE)
        return jsonResponse(PAGES)
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('поиск и каталог; клик по статье открывает текст со ссылками', async () => {
    render(<WikiSection />)
    expect(screen.getByText(/Летопись Теслы/i)).toBeTruthy()
    const catalog = (): HTMLElement => document.querySelector('[aria-label="Каталог статей"]') as HTMLElement
    await waitFor(() => expect(within(catalog()).getByText('СПО «Юность»')).toBeTruthy())
    // поиск фильтрует каталог
    fireEvent.change(screen.getByPlaceholderText(/Найти статью/i), { target: { value: 'Юность' } })
    await waitFor(() => expect(within(catalog()).queryByText('Богачёв Егор')).toBeNull())
    fireEvent.change(screen.getByPlaceholderText(/Найти статью/i), { target: { value: '' } })
    // клик по статье открывает markdown с вики-ссылкой
    fireEvent.click(within(catalog()).getByText('СПО «Юность»').closest('button')!)
    await waitFor(() => expect(screen.getByText(/Командир/i)).toBeTruthy())
    expect(screen.getAllByText('Богачёв Егор').some((el) => el.tagName === 'BUTTON')).toBe(true)
    // wall-ID показан как «пост VK», служебный раздел скрыт
    const vkLinks = screen.getAllByText('пост VK')
    expect(vkLinks.length).toBeGreaterThanOrEqual(1)
    expect(vkLinks.every((el) => el.tagName === 'A')).toBe(true)
    expect(screen.queryByText(/wall-198864697_133/)).toBeNull()
    expect(screen.queryByText(/Источники данных/)).toBeNull()
    expect(screen.queryByText(/posts_spoyunost2020/)).toBeNull()
    // URL статьи — отдельная страница
    expect(window.location.pathname).toBe('/wiki/lso/spo_yunost')
  })

  it('глубокая ссылка /wiki/<slug> открывает статью сразу', async () => {
    window.history.pushState({}, '', '/wiki/lso/spo_yunost')
    try {
      render(<WikiSection />)
      await waitFor(() => expect(screen.getByText(/Командир/i)).toBeTruthy())
    } finally {
      window.history.pushState({}, '', '/')
    }
  })
})
