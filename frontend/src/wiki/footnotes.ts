/** Препроцесс вики-текста: [[ссылки]] -> markdown, цитаты постов VK -> сноски [n], автолинковка упоминаний. */

export interface FootRef {
  n: number
  url: string
  label: string
}

export interface LinkEntry {
  title: string
  slug: string
}

const VK_URL = /https?:\/\/(?:www\.|m\.)?vk\.com\/[^\s<>"')\]]+/
const VK_URL_G = new RegExp(VK_URL.source, 'g')
const PUB_DATE = /опубл\.\s*(\d{4}-\d{2}-\d{2})/
/** (Источник: …) с двумя уровнями скобок — покрывает ([wall](url)) внутри. */
const CITE_RE = /\(Источник:\s*(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)/g
const MD_LINK_VK = /\[([^\]]*)\]\((https?:\/\/(?:www\.|m\.)?vk\.com\/[^)\s]+)\)/g
const WIKI_LINK = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g
/** [https://…] без (url) — артефакт ответов, а не ссылка. */
const BRACKETED_URL = /\[((?:https?:\/\/)[^\]\s]+)\]/g

function cleanUrl(url: string): string {
  return url.replace(/[.,!?;:]+$/, '')
}

/** [[slug|лейбл]] -> [лейбл](/wiki/slug). */
export function wikiLinksToMd(md: string): string {
  return md.replace(WIKI_LINK, (_, slug: string, label: string | undefined) => `[${label ?? slug}](/wiki/${slug})`)
}

/** [https://…] -> https://… (голый URL дальше подхватит GFM-автолинк). */
export function unwrapBracketedUrls(md: string): string {
  return md.replace(BRACKETED_URL, '$1')
}

/** (Источник: …) вырезать целиком (для инфобокса: детали остаются в теле статьи). */
export function stripCites(md: string): string {
  return md
    .replace(CITE_RE, '')
    .replace(/\s+([.,;:!?])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
}

/**
 * Цитаты постов VK -> компактные сноски [n](#ref-n).
 * Возвращает текст и нумерованный список источников (порядок первого упоминания, повторы — тот же номер).
 */
export function extractFootnotes(md: string): { text: string; refs: FootRef[] } {
  const refs: FootRef[] = []
  const seen = new Map<string, number>()
  const ref = (url: string, label: string): string => {
    let n = seen.get(url)
    if (n === undefined) {
      n = refs.length + 1
      seen.set(url, n)
      refs.push({ n, url, label })
    }
    return `[${n}](#ref-${n})`
  }

  // 1. Целые (Источник: …) с VK-ссылками -> маркеры; подпись — максимально короткая: дата публикации.
  let text = md.replace(CITE_RE, (span) => {
    const urls = [...new Set([...span.matchAll(VK_URL_G)].map((m) => cleanUrl(m[0])))]
    if (urls.length === 0) return span
    const date = PUB_DATE.exec(span)?.[1]
    const label = date ? `VK · ${date}` : 'VK-пост'
    return urls.map((u) => ref(u, label)).join('')
  })
  // 2. Остаточные [текст](vk-url) и голые vk-URL вне цитат.
  text = text.replace(MD_LINK_VK, (_, label: string, url: string) => {
    const t = label.trim()
    return ref(cleanUrl(url), t && !/wall-?\d+_\d+/.test(t) ? t : 'VK-пост')
  })
  text = text.replace(VK_URL_G, (url) => ref(cleanUrl(url), 'VK-пост'))
  return { text, refs }
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/**
 * Упоминания известных статей (имена, отряды) -> ссылки на /wiki/slug.
 * Не трогает код, готовые ссылки и [[…]]; самое длинное совпадение побеждает; себя не линкует.
 */
export function autolinkMentions(md: string, entries: LinkEntry[], skipSlug?: string): string {
  const list = entries.filter((e) => e.title && e.slug && e.slug !== skipSlug).sort((a, b) => b.title.length - a.title.length)
  if (list.length === 0) return md
  const byTitle = new Map(list.map((e) => [e.title, e.slug]))
  const re = new RegExp(`(?<![\\p{L}\\p{N}_])(${list.map((e) => escapeRegExp(e.title)).join('|')})(?![\\p{L}\\p{N}_])`, 'gu')
  return md
    .split(/(`[^`]*`|\[[^\]]*\]\([^)]*\)|\[\[[^\]]+\]\])/g)
    .map((part, i) => (i % 2 === 1 ? part : part.replace(re, (m) => `[${m}](/wiki/${byTitle.get(m)})`)))
    .join('')
}
