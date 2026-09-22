export type WikiTextPart =
  | { type: 'text'; text: string }
  | { type: 'link'; slug: string; label: string }

const WIKI_LINK_RE = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g

/** Разбивает текст на обычные куски и [[slug|лейбл]]-ссылки. */
export function parseWikiLinks(text: string): WikiTextPart[] {
  const parts: WikiTextPart[] = []
  let last = 0
  let m: RegExpExecArray | null
  WIKI_LINK_RE.lastIndex = 0
  while ((m = WIKI_LINK_RE.exec(text)) !== null) {
    if (m.index > last) parts.push({ type: 'text', text: text.slice(last, m.index) })
    parts.push({ type: 'link', slug: m[1], label: m[2] ?? m[1] })
    last = m.index + m[0].length
  }
  if (last < text.length) parts.push({ type: 'text', text: text.slice(last) })
  return parts
}

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
