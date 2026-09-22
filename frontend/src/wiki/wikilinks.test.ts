import { describe, expect, it } from 'vitest'

import { categoryOf } from './wikilinks'

describe('categoryOf', () => {
  it('persons/* -> person, lso/* -> squad, остальное -> корень', () => {
    expect(categoryOf('persons/ivanov_ivan')).toBe('person')
    expect(categoryOf('lso/spo_yunost')).toBe('squad')
    expect(categoryOf('hq/index')).toBe('hq')
    expect(categoryOf('index')).toBe('wiki')
  })
})
