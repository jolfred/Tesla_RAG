import { describe, expect, it } from 'vitest'

import { categoryOf, extractInfobox, extractToc, slugifyHeading } from './wikilinks'

describe('categoryOf', () => {
  it('persons/* -> person, lso/* -> squad, остальное -> корень', () => {
    expect(categoryOf('persons/ivanov_ivan')).toBe('person')
    expect(categoryOf('lso/spo_yunost')).toBe('squad')
    expect(categoryOf('hq/index')).toBe('hq')
    expect(categoryOf('index')).toBe('wiki')
  })

  it('bare-kind без слэша не схлопывается в wiki', () => {
    expect(categoryOf('squad')).toBe('squad')
    expect(categoryOf('person')).toBe('person')
    expect(categoryOf('hq')).toBe('hq')
  })
})

describe('slugifyHeading', () => {
  it('кириллица и латиница -> якорь', () => {
    expect(slugifyHeading('Награды и достижения')).toBe('награды_и_достижения')
    expect(slugifyHeading('Целина 2021: итоги!')).toBe('целина_2021_итоги')
  })
})

describe('extractToc', () => {
  it('## -заголовки -> пункты содержания, служебный раздел пропущен', () => {
    expect(extractToc('# Т\n\n## Командный состав\n\nтекст\n\n### Детали\n\n## Источники данных\n')).toEqual([
      { id: 'командный_состав', text: 'Командный состав' },
      { id: 'детали', text: 'Детали' },
    ])
  })
})

describe('extractInfobox', () => {
  it('ведущие «- **Ключ:** значение» -> строки карточки, остальное — тело', () => {
    const { rows, rest } = extractInfobox(
      '# СПО «Юность»\n\n- **Направление:** СПО\n- **Девиз:** «Раскрась!»\n\n## Хронология\n\nтекст\n',
    )
    expect(rows).toEqual([
      { k: 'Направление', v: 'СПО' },
      { k: 'Девиз', v: '«Раскрась!»' },
    ])
    expect(rest).toBe('# СПО «Юность»\n\n## Хронология\n\nтекст\n')
  })

  it('без мета-буллитов — пусто, текст цел', () => {
    const { rows, rest } = extractInfobox('# Т\n\nПросто текст.\n')
    expect(rows).toEqual([])
    expect(rest).toBe('# Т\n\nПросто текст.\n')
  })
})
