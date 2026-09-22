import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { WikiNode, WikiPageData } from '../types'
import { autolinkMentions, extractFootnotes, wikiLinksToMd, type FootRef, type LinkEntry } from './footnotes'
import { Markdown } from './markdown'
import { categoryOf } from './wikilinks'

/** Frontmatter и служебный раздел «Источники данных» (локальные пути) вырезаны. */
function stripService(markdown: string): string {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, '')
  const lines: string[] = []
  let skip = false
  for (const line of body.split('\n')) {
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) skip = h[2].trim().toLowerCase() === 'источники данных'
    if (!skip) lines.push(line)
  }
  return lines.join('\n')
}

function ArticleView({ article, entries }: { article: WikiPageData; entries: LinkEntry[] }): React.JSX.Element {
  const { text, refs } = useMemo(() => {
    let body = stripService(article.markdown)
    if (!/^#\s/m.test(body)) body = `# ${article.slug}\n\n${body}`
    return extractFootnotes(autolinkMentions(wikiLinksToMd(body), entries, article.slug))
  }, [article, entries])

  return (
    <article>
      <div style={{ marginTop: 16, fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#6D28D9' }}>
        {categoryOf(article.slug)}
      </div>
      <Markdown text={text} tone="light" />
      {refs.length > 0 && <Notes refs={refs} />}
      <div style={{ marginTop: 32 }}>
        <a href="/wiki" style={{ display: 'inline-block', fontSize: 14, fontWeight: 700, color: '#fff', background: '#7A3EE6', borderRadius: 999, padding: '12px 24px', textDecoration: 'none' }}>
          ← Все статьи
        </a>
      </div>
    </article>
  )
}

/** Примечания: короткие подписи вида «VK · 2021-04-07», ↩ возвращает к маркеру в тексте. */
function Notes({ refs }: { refs: FootRef[] }): React.JSX.Element {
  return (
    <section style={{ marginTop: 32, borderTop: '1px solid #E7DFD2', paddingTop: 16 }}>
      <h2 style={{ fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6D28D9', margin: '0 0 10px' }}>
        Примечания
      </h2>
      <ol style={{ margin: 0, paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {refs.map((r) => (
          <li key={r.n} id={`ref-${r.n}`} style={{ fontSize: 14, color: '#3D352D' }}>
            <a href={r.url} target="_blank" rel="noreferrer" style={{ color: '#6D28D9', overflowWrap: 'anywhere' }}>
              {r.label}
            </a>{' '}
            <a href={`#fnref-${r.n}`} aria-label="Вернуться к тексту" style={{ color: '#ABA094', textDecoration: 'none' }}>
              ↩
            </a>
          </li>
        ))}
      </ol>
    </section>
  )
}

export default function WikiArticle({ slug }: { slug: string }): React.JSX.Element {
  const [article, setArticle] = useState<WikiPageData | null>(null)
  const [entries, setEntries] = useState<LinkEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    let alive = true
    setArticle(null)
    setMissing(false)
    setLoading(true)
    api
      .wikiPage(slug)
      .then((a) => {
        if (!alive) return
        setArticle(a)
        setLoading(false)
      })
      .catch(() => {
        if (!alive) return
        setLoading(false)
        setMissing(true)
      })
    api
      .wikiPages()
      .then((p) => {
        if (!alive) return
        setEntries((p.pages ?? []).map((n: WikiNode) => ({ title: n.title, slug: n.slug })))
      })
      .catch(() => {
        /* без каталога — просто без автолинковки упоминаний */
      })
    return () => {
      alive = false
    }
  }, [slug])

  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '40px 20px 80px' }}>
      <a href="/wiki" style={{ fontSize: 14, fontWeight: 700, color: '#6D28D9', textDecoration: 'none' }}>
        ← Все статьи
      </a>
      {loading && <div style={{ marginTop: 24, color: '#6F6459', fontSize: 15 }}>Открываем статью…</div>}
      {!loading && missing && <div style={{ marginTop: 24, color: '#B3261E', fontSize: 15 }}>Такой статьи в Летописи нет.</div>}
      {!loading && article && <ArticleView article={article} entries={entries} />}
    </div>
  )
}
