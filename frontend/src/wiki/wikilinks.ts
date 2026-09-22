import type { WikiEdge, WikiNode } from '../types'

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

/** Нормализованная категория страницы по слагу (для цвета в графе и фильтров). */
export function categoryOf(slug: string): string {
  const head = slug.includes('/') ? slug.split('/')[0] : 'wiki'
  return CATEGORY_ALIAS[head] ?? head
}

/** Цвет категории: монохромная фиолетовая шкала + нейтрали (акцент страницы один). */
export const CATEGORY_COLORS: Record<string, string> = {
  squad: '#9D65FF',
  person: '#C9B8FF',
  hq: '#7A3EE6',
  event: '#8E86A8',
  heritage: '#6E6589',
  methodology: '#5C5470',
  project: '#B9B0D6',
  camp: '#A79BDE',
  wiki: '#EAE4FF',
}

export function categoryColor(kind: string): string {
  return CATEGORY_COLORS[categoryOf(kind)] ?? '#8E86A8'
}

/**
 * Раскладка без физики: категории — сектора круга, люди — внешнее кольцо.
 * Детерминирована, O(n). Пружины — только если кругов станет мало.
 * ponytail: O(n^2)-физика и Barnes-Hut — когда узлов станут тысячи.
 */
export function layoutGraph(
  nodes: WikiNode[],
  edges: WikiEdge[],
  width: number,
  height: number,
): Record<string, [number, number]> {
  void edges
  const cx = width / 2
  const cy = height / 2
  const R = Math.min(width, height) / 2 - 30
  const out: Record<string, [number, number]> = {}
  const groups = new Map<string, WikiNode[]>()
  for (const n of nodes) {
    const c = categoryOf(n.kind)
    if (!groups.has(c)) groups.set(c, [])
    groups.get(c)!.push(n)
  }
  const cats = [...groups.keys()]
  groups.forEach((members, c) => {
    const base = (cats.indexOf(c) / Math.max(1, cats.length)) * Math.PI * 2
    const r = R * (c === 'person' ? 0.95 : 0.55)
    members.forEach((n, i) => {
      const a = base + (i / members.length) * Math.PI * 2
      out[n.slug] = [
        Math.min(width - 16, Math.max(16, cx + Math.cos(a) * r)),
        Math.min(height - 16, Math.max(16, cy + Math.sin(a) * r * (height / width))),
      ]
    })
  })
  return out
}
