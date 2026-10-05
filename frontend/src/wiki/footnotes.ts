/** Препроцесс вики-текста: [[ссылки]] -> markdown, цитаты постов VK -> сноски [n], автолинковка упоминаний. */

export interface FootRef {
  n: number
  url: string
  label: string
  markers: string[]
}

export interface SourceDetails {
  url: string
  title?: string | null
  group_name?: string | null
  topic?: string | null
  group?: string | null
  published_at?: string | null
  event_date?: string | null
}

export interface LinkEntry {
  title: string
  slug: string
}

const VK_URL = /(?:https?:\/\/(?:www\.|m\.)?vk\.com\/|\/api\/v1\/wiki\/source\?ref=)[^\s<>"')\]]+/
const VK_URL_G = new RegExp(VK_URL.source, 'g')
const PUB_DATE = /опубл\.\s*(\d{4}-\d{2}-\d{2})/
/** (Источник: …) с двумя уровнями скобок — покрывает ([wall](url)) внутри. */
const CITE_RE = /\(Источник:\s*(?:[^()]|\((?:[^()]|\([^()]*\))*\))*\)/g
const MD_LINK_VK = /\[([^\]]*)\]\(((?:https?:\/\/(?:www\.|m\.)?vk\.com\/|\/api\/v1\/wiki\/source\?ref=)[^)\s]+)\)/g
const WIKI_LINK = /\[\[([^\]|]+)(?:\|([^\]]+))?\]\]/g
/** [https://…] без (url) — артефакт ответов, а не ссылка. */
const BRACKETED_URL = /\[((?:https?:\/\/)[^\]\s]+)\]/g

function cleanUrl(url: string): string {
  return url.replace(/[.,!?;:]+$/, '')
}

function humanizeDomain(domain: string): string {
  const known: Record<string, string> = {
    rso_tesla: 'Штаб «Тесла»', spoyunost2020: 'СПО «Юность»', dainima: 'ССО «Дайнима»',
    sso_isida: 'ССО «Исида»', spodelta: 'СПО «Дельта»', sservoonyx: 'ССервО «Оникс»',
    osd_sirius21: 'ОСД «Сириус»', seo_vysokoe_napryazhenie: 'СЭО «Высокое Напряжение»',
  }
  return known[domain] ?? domain.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function sourceLabel(url: string, details?: SourceDetails, citation?: string, fallback?: string): string {
  const topic = details?.topic?.trim() || details?.title?.trim() ||
    (/опубл\.\s*\d{4}-\d{2}-\d{2}\s*[—–-]\s*([^;`)]+)/i.exec(citation ?? '')?.[1]?.trim()) ||
    (fallback && !/wall-?\d+_\d+|archive:|group:|https?:/i.test(fallback) ? fallback : '')
  const group = details?.group_name?.trim() || details?.group?.trim() || (url.startsWith('/api/v1/wiki/source?ref=') ? 'Архив Штаба' : humanizeDomain(/vk\.com\/([^/?#]+)/i.exec(url)?.[1] ?? 'Сообщество ВКонтакте'))
  const date = details?.published_at?.slice(0, 10) || PUB_DATE.exec(citation ?? '')?.[1]
  return [topic || 'Публикация', group, date].filter(Boolean).join(' · ')
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
export function extractFootnotes(md: string, sources: SourceDetails[] = []): { text: string; refs: FootRef[] } {
  const refs: FootRef[] = []
  const seen = new Map<string, number>()
  const detailsByUrl = new Map(sources.map((s) => [cleanUrl(s.url), s]))
  let markerCount = 0
  const ref = (url: string, label: string, citation?: string): string => {
    let n = seen.get(url)
    if (n === undefined) {
      n = refs.length + 1
      seen.set(url, n)
      refs.push({ n, url, label: sourceLabel(url, detailsByUrl.get(url), citation, label), markers: [] })
    }
    markerCount += 1
    const marker = `${n}-${markerCount}`
    refs[n - 1].markers.push(marker)
    return `[${n}](#ref-${marker})`
  }

  // 1. Целые (Источник: …) с VK-ссылками -> маркеры; подпись — максимально короткая: дата публикации.
  // Старые статьи часто оборачивали всю ячейку с источником в inline code.
  let text = md.replace(/`([^`\n]*(?:Источник:|wall-?\d+_\d+|https?:\/\/(?:www\.|m\.)?vk\.com\/)[^`\n]*)`/gi, (_, inner: string) => {
    const url = inner.match(VK_URL_G)?.map(cleanUrl)[0]
    if (!url || /Источник:/i.test(inner)) return inner
    const date = /(\d{4}-\d{2}-\d{2})/.exec(inner)?.[1]
    const topic = date ? new RegExp(`${escapeRegExp(date)}\\s*[—–-]\\s*(.+?)\\s*$`).exec(inner)?.[1]?.trim() : ''
    const context = `${date ? `опубл. ${date}` : ''}${topic ? `${date ? ' — ' : ''}${topic}` : ''}`
    return ref(url, '', context)
  })
  text = text.replace(CITE_RE, (span) => {
    const urls = [...new Set([...span.matchAll(VK_URL_G)].map((m) => cleanUrl(m[0])))]
    if (urls.length === 0) return span
    return urls.map((u) => ref(u, '', span)).join('')
  })
  // 2. Остаточные [текст](vk-url) и голые vk-URL вне цитат.
  text = text.replace(MD_LINK_VK, (_, label: string, url: string) => {
    const t = label.trim()
    return ref(cleanUrl(url), t && !/wall-?\d+_\d+/.test(t) ? t : '')
  })
  text = text.replace(VK_URL_G, (url) => ref(cleanUrl(url), ''))
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
