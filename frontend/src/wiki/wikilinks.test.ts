import { describe, expect, it } from 'vitest'

import { categoryOf, parseWikiLinks } from './wikilinks'

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
