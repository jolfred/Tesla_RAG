import { describe, expect, it } from 'vitest'

import { categoryOf, layoutGraph, parseWikiLinks } from './wikilinks'
import type { WikiEdge, WikiNode } from '../types'

describe('parseWikiLinks', () => {
  it('разбирает [[slug|лейбл]] и [[slug]]', () => {
    const parts = parseWikiLinks('Был избран [[persons/bogachev_egor|Богачёв Егор]] и [[hq/index]] рядом.')
    expect(parts).toEqual([
      { type: 'text', text: 'Был избран ' },
      { type: 'link', slug: 'persons/bogachev_egor', label: 'Богачёв Егор' },
      { type: 'text', text: ' и ' },
      { type: 'link', slug: 'hq/index', label: 'hq/index' },
      { type: 'text', text: ' рядом.' },
    ])
  })

  it('текст без ссылок — один кусок', () => {
    expect(parseWikiLinks('просто текст')).toEqual([{ type: 'text', text: 'просто текст' }])
  })
})

describe('categoryOf', () => {
  it('persons/* -> person, lso/* -> squad, остальное -> корень', () => {
    expect(categoryOf('persons/ivanov_ivan')).toBe('person')
    expect(categoryOf('lso/spo_yunost')).toBe('squad')
    expect(categoryOf('hq/index')).toBe('hq')
    expect(categoryOf('index')).toBe('wiki')
  })
})

describe('layoutGraph', () => {
  const nodes: WikiNode[] = [
    { slug: 'lso/spo_yunost', title: 'СПО «Юность»', kind: 'squad' },
    { slug: 'persons/bogachev_egor', title: 'Богачёв Егор', kind: 'person' },
    { slug: 'hq/index', title: 'Штаб', kind: 'hq' },
  ]
  const edges: WikiEdge[] = [{ source: 'lso/spo_yunost', target: 'persons/bogachev_egor' }]

  it('детерминирован, все в границах, позиции разные', () => {
    const a = layoutGraph(nodes, edges, 600, 400)
    expect(a).toEqual(layoutGraph(nodes, edges, 600, 400))
    const pts = Object.values(a)
    expect(pts).toHaveLength(3)
    for (const [x, y] of pts) {
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThanOrEqual(600)
      expect(y).toBeGreaterThanOrEqual(0)
      expect(y).toBeLessThanOrEqual(400)
    }
    expect(new Set(pts.map(([x, y]) => `${Math.round(x)},${Math.round(y)}`)).size).toBe(3)
  })
})
