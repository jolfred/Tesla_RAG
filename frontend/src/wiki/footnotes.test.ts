import { describe, expect, it } from 'vitest'

import { autolinkMentions, extractFootnotes, stripCites, unwrapBracketedUrls, wikiLinksToMd } from './footnotes'

describe('wikiLinksToMd', () => {
  it('[[slug|лейбл]] и [[slug]] -> markdown-ссылки на /wiki/', () => {
    expect(wikiLinksToMd('избран [[persons/bogachev_egor|Богачёв Егор]] и [[hq/index]]')).toBe(
      'избран [Богачёв Егор](/wiki/persons/bogachev_egor) и [hq/index](/wiki/hq/index)',
    )
  })
})

describe('extractFootnotes', () => {
  it('(Источник: ([wall](url)), опубл. дата) -> [1], подпись VK · дата', () => {
    const { text, refs } = extractFootnotes(
      'избран Егор (Источник: ([wall-198864697_133](https://vk.com/spoyunost2020?w=wall-198864697_133)), опубл. 2021-04-07, событие 2021-04-07).',
    )
    expect(text).toBe('избран Егор [1](#ref-1).')
    expect(refs).toEqual([{ n: 1, url: 'https://vk.com/spoyunost2020?w=wall-198864697_133', label: 'VK · 2021-04-07' }])
  })

  it('повтор того же поста — тот же номер, wall-ID нигде в тексте', () => {
    const { text, refs } = extractFootnotes(
      'а (Источник: ([wall-1_2](https://vk.com/g?w=wall-1_2)), опубл. 2022-01-01) и б (Источник: ([wall-1_2](https://vk.com/g?w=wall-1_2)), опубл. 2022-01-01).',
    )
    expect(text).toBe('а [1](#ref-1) и б [1](#ref-1).')
    expect(refs).toHaveLength(1)
    expect(text).not.toContain('wall-1_2')
  })

  it('цитата без URL и обычный текст — как есть', () => {
    const { text, refs } = extractFootnotes('факт (Источник: описание группы `../groups/g.json`).')
    expect(text).toContain('описание группы')
    expect(refs).toHaveLength(0)
  })

  it('не-VK ссылки не трогает', () => {
    const { text, refs } = extractFootnotes('см. [документ](https://example.com/a.pdf).')
    expect(text).toContain('[документ](https://example.com/a.pdf)')
    expect(refs).toHaveLength(0)
  })
})

describe('autolinkMentions', () => {
  const entries = [
    { title: 'Богачёв Егор', slug: 'persons/bogachev_egor' },
    { title: 'СПО «Юность»', slug: 'lso/spo_yunost' },
  ]

  it('упоминания -> ссылки на /wiki, себя пропускает', () => {
    expect(autolinkMentions('Командир Богачёв Егора нет, а Богачёв Егор да.', entries, 'lso/spo_yunost')).toBe(
      'Командир Богачёв Егора нет, а [Богачёв Егор](/wiki/persons/bogachev_egor) да.',
    )
  })

  it('код и готовые ссылки не трогает', () => {
    expect(autolinkMentions('`Богачёв Егор` и [Богачёв Егор](https://vk.com/x)', entries)).toBe(
      '`Богачёв Егор` и [Богачёв Егор](https://vk.com/x)',
    )
  })
})

describe('unwrapBracketedUrls', () => {
  it('[https://…] -> голый URL', () => {
    expect(unwrapBracketedUrls('штаб [https://vk.com/rso_tesla?w=wall-1_2]. Приходи!')).toBe('штаб https://vk.com/rso_tesla?w=wall-1_2. Приходи!')
  })
})

describe('stripCites', () => {
  it('(Источник: …) вырезан целиком для инфобокса', () => {
    expect(stripCites('07.10.2020 (Источник: описание группы `../groups/g.json`), девиз «Вперёд!»')).toBe(
      '07.10.2020, девиз «Вперёд!»',
    )
  })
})
