const CATEGORY_ALIAS: Record<string, string> = {
  persons: 'person',
  lso: 'squad',
  projects: 'project',
  index: 'wiki',
}

/** Нормализованная категория страницы по слагу (для фильтров каталога). */
export function categoryOf(slug: string): string {
  const head = slug.includes('/') ? slug.split('/')[0] : 'wiki'
  return CATEGORY_ALIAS[head] ?? head
}
