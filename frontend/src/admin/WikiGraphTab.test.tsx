import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import WikiGraphTab from './WikiGraphTab'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('WikiGraphTab', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('uses Wiki page nodes and links, with article links to the public Wiki', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({
      nodes: [{ slug: 'lso/spo_yunost', title: 'СПО «Юность»', kind: 'squad' }],
      edges: [{ source: 'lso/spo_yunost', target: 'persons/bogachev_egor' }],
    })))
    render(<WikiGraphTab />)
    expect(await screen.findByText('1 статей · 1 ссылок')).toBeTruthy()
    const article = screen.getAllByRole('link', { name: 'СПО «Юность»' })[0]
    expect(article.getAttribute('href')).toBe('/wiki/lso/spo_yunost')
    expect(screen.getByRole('img', { name: 'Граф статей Летописи' })).toBeTruthy()
  })
})
