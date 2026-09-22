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
const GRAPH = {
  nodes: PAGES.pages,
  edges: [{ source: 'lso/spo_yunost', target: 'persons/bogachev_egor' }],
}
const ARTICLE = {
  status: 'success',
  slug: 'lso/spo_yunost',
  markdown: '# СПО «Юность»\n\nКомандир — [[persons/bogachev_egor|Богачёв Егор]].\n',
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
        if (url.includes('/api/v1/wiki/graph')) return jsonResponse(GRAPH)
        if (url.includes('/api/v1/wiki/pages')) return jsonResponse(PAGES)
        if (url.includes('/api/v1/wiki/page')) return jsonResponse(ARTICLE)
        if (url.includes('/api/v1/wiki/search')) return jsonResponse({ status: 'success', items: [] })
        return jsonResponse(PAGES)
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('рендерит граф, поиск и каталог; клик по статье открывает текст со ссылками', async () => {
    render(<WikiSection />)
    expect(screen.getByText(/Летопись Теслы/i)).toBeTruthy()
    // граф отрисовался
    await waitFor(() => expect(document.querySelector('svg.wiki-graph')).toBeTruthy())
    // поиск фильтрует каталог (ищем внутри каталога: SVG-граф тоже содержит <title> с именами)
    const catalog = (): HTMLElement => document.querySelector('[aria-label="Каталог статей"]') as HTMLElement
    const search = screen.getByPlaceholderText(/Найти статью/i)
    fireEvent.change(search, { target: { value: 'Юность' } })
    await waitFor(() => expect(within(catalog()).queryByText('Богачёв Егор')).toBeNull())
    fireEvent.change(search, { target: { value: '' } })
    // клик по статье открывает markdown с вики-ссылкой
    fireEvent.click(within(catalog()).getByText('СПО «Юность»').closest('button')!)
    await waitFor(() => expect(screen.getByText(/Командир/i)).toBeTruthy())
    const egorLinks = screen.getAllByText('Богачёв Егор')
    expect(egorLinks.some((el) => el.tagName === 'BUTTON')).toBe(true)
  })
})
