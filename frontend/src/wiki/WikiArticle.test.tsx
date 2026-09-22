import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WikiArticle from './WikiArticle'

const ARTICLE = {
  status: 'success',
  slug: 'lso/spo_yunost',
  markdown:
    '# СПО «Юность»\n\nКомандир — [[persons/bogachev_egor|Богачёв Егор]] ' +
    '(Источник: ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)), опубл. 2021-04-07).\n' +
    '\n## Источники данных\n\n- `../posts/posts_spoyunost2020.jsonl`\n',
  links: ['persons/bogachev_egor'],
  sources: [
    'https://vk.com/spoyunost2020?w=wall-198864697_133',
    'https://vk.com/spoyunost2020?w=wall-198864697_640',
  ],
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

describe('WikiArticle', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(ARTICLE)),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('статья: заголовок, вики-ссылки, «пост VK», без служебного раздела', async () => {
    render(<WikiArticle slug="lso/spo_yunost" />)
    expect(await screen.findByRole('heading', { name: 'СПО «Юность»' })).toBeTruthy()
    // [[ссылка]] ведёт на отдельную страницу статьи
    const person = screen.getByRole('link', { name: 'Богачёв Егор' })
    expect(person.getAttribute('href')).toBe('/wiki/persons/bogachev_egor')
    // wall-ID нигде, служебный раздел скрыт
    expect(screen.queryByText(/wall-198864697/)).toBeNull()
    expect(screen.queryByText(/Источники данных/)).toBeNull()
    expect(screen.queryByText(/posts_spoyunost2020/)).toBeNull()
    // источники пронумерованы
    expect(screen.getByRole('link', { name: 'пост VK · 1' })).toBeTruthy()
    expect(screen.getAllByRole('link', { name: '← Все статьи' }).length).toBeGreaterThanOrEqual(1)
  })

  it('битый слаг — «нет такой статьи»', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ status: 'fail' }, 404)))
    render(<WikiArticle slug="no/such" />)
    expect(await screen.findByText(/Такой статьи в Летописи нет/i)).toBeTruthy()
  })
})
