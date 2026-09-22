import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import WikiCatalog from './WikiCatalog'

const PAGES = {
  pages: [
    { slug: 'lso/spo_yunost', title: 'СПО «Юность»', kind: 'squad' },
    { slug: 'persons/bogachev_egor', title: 'Богачёв Егор', kind: 'person' },
    { slug: 'hq/index', title: 'Штаб СО КГЭУ «Тесла»', kind: 'hq' },
  ],
}

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('WikiCatalog', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(PAGES)),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('список статей со ссылками на отдельные страницы; поиск фильтрует', async () => {
    render(<WikiCatalog />)
    const list = await screen.findByRole('list', { name: 'Каталог статей' })
    const link = within(list).getByRole('link', { name: /СПО «Юность»/ })
    expect(link.getAttribute('href')).toBe('/wiki/lso/spo_yunost')
    fireEvent.change(screen.getByPlaceholderText(/Найти статью/i), { target: { value: 'Юность' } })
    await waitFor(() => expect(within(list).queryByRole('link', { name: /Богачёв Егор/ })).toBeNull())
    expect(within(list).getByRole('link', { name: /СПО «Юность»/ })).toBeTruthy()
  })

  it('ошибка загрузки — понятное сообщение', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response('err', { status: 500 })))
    render(<WikiCatalog />)
    expect(await screen.findByText(/Не удалось загрузить/i)).toBeTruthy()
  })
})
