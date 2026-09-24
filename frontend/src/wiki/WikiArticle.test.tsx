import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WikiArticle from './WikiArticle'

const ARTICLE = {
  status: 'success',
  slug: 'lso/spo_yunost',
  markdown:
    '# СПО «Юность»\n\n- **Направление:** СПО\n- **Девиз:** «Раскрась!»\n' +
    '\nКомандир — [[persons/bogachev_egor|Богачёв Егор]] ' +
    '(Источник: ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)), опубл. 2021-04-07).\n' +
    '\n## Хронология\n\nТекст.\n\n## Награды\n\nТекст.\n' +
    '\n## Источники данных\n\n- `../posts/posts_spoyunost2020.jsonl`\n',
  links: ['persons/bogachev_egor'],
  sources: [
    'https://vk.com/spoyunost2020?w=wall-198864697_133',
    'https://vk.com/spoyunost2020?w=wall-198864697_640',
  ],
}

const PAGES = {
  pages: [{ slug: 'persons/bogachev_egor', title: 'Богачёв Егор', kind: 'person' }],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mockFetch(article: object): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/wiki/pages')) return jsonResponse(PAGES)
      return jsonResponse(article)
    }),
  )
}

describe('WikiArticle', () => {
  beforeEach(() => {
    mockFetch(ARTICLE)
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('статья: заголовок, вики-ссылки, сноска вместо цитаты, без служебного раздела', async () => {
    render(<WikiArticle slug="lso/spo_yunost" />)
    expect(await screen.findByRole('heading', { name: 'СПО «Юность»' })).toBeTruthy()
    // [[ссылка]] ведёт на отдельную страницу статьи
    const person = screen.getByRole('link', { name: 'Богачёв Егор' })
    expect(person.getAttribute('href')).toBe('/wiki/persons/bogachev_egor')
    // цитата свернута в сноску [1], wall-ID нигде, служебный раздел скрыт
    const note = screen.getByRole('link', { name: '[1]' })
    expect(note.getAttribute('href')).toBe('#ref-1')
    expect(screen.queryByText(/wall-198864697/)).toBeNull()
    expect(screen.queryByText(/Источники данных/)).toBeNull()
    expect(screen.queryByText(/posts_spoyunost2020/)).toBeNull()
    // примечания — короткая подпись со ссылкой на пост
    expect(screen.getByText('Примечания')).toBeTruthy()
    const ref = screen.getByRole('link', { name: 'VK · 2021-04-07' })
    expect(ref.getAttribute('href')).toBe('https://vk.com/spoyunost2020?w=wall-198864697_133')
    expect(screen.getAllByRole('link', { name: '← Все статьи' })).toHaveLength(2)
  })

  it('инфобокс из мета-буллитов и содержание с якорями', async () => {
    render(<WikiArticle slug="lso/spo_yunost" />)
    await screen.findByRole('heading', { name: 'СПО «Юность»' })
    const card = screen.getByRole('complementary', { name: 'Карточка статьи' })
    expect(card.textContent).toContain('Направление')
    expect(card.textContent).toContain('СПО')
    expect(card.textContent).not.toContain('Хронология')
    const toc = screen.getByRole('navigation', { name: 'Содержание' })
    const link = Array.from(toc.querySelectorAll('a')).find((a) => a.textContent?.includes('Хронология'))
    expect(link?.getAttribute('href')).toBe('#хронология')
    expect(document.getElementById('хронология')?.tagName).toBe('H2')
  })

  it('упоминание персоны без [[ ]] само становится ссылкой на вики', async () => {
    mockFetch({ ...ARTICLE, markdown: '# Тест\n\nКомандир Богачёв Егор работает.\n' })
    render(<WikiArticle slug="lso/test" />)
    expect(await screen.findByRole('heading', { name: 'Тест' })).toBeTruthy()
    const person = screen.getByRole('link', { name: 'Богачёв Егор' })
    expect(person.getAttribute('href')).toBe('/wiki/persons/bogachev_egor')
  })

  it('битый слаг — «нет такой статьи»', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'fail' }, 404)))
    render(<WikiArticle slug="no/such" />)
    expect(await screen.findByText(/Такой статьи в Летописи нет/i)).toBeTruthy()
  })
})
