import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { WikiNode, WikiPageData } from '../types'
import { autolinkMentions, extractFootnotes, stripCites, wikiLinksToMd, type FootRef, type LinkEntry } from './footnotes'
import { Markdown } from './markdown'
import { categoryOf, extractInfobox, extractToc, type InfoRow, type TocEntry } from './wikilinks'

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
  const { title, lead, rest, toc, rows, refs } = useMemo(() => {
    const stripped = stripService(article.markdown)
    const { rows, rest: noBox } = extractInfobox(stripped)
    const toc = extractToc(noBox)
    const full = extractFootnotes(autolinkMentions(wikiLinksToMd(noBox), entries, article.slug))
    // Заголовок отдельно, лид — до первого ##, остальное — после (сноски нумеруются сквозно).
    const m = /^#\s+(.+?)\s*$/m.exec(full.text)
    const title = m ? m[1] : article.slug
    const withoutTitle = m ? full.text.replace(m[0], '') : full.text
    const cut = withoutTitle.search(/^##\s/m)
    const lead = cut === -1 ? withoutTitle : withoutTitle.slice(0, cut)
    const rest = cut === -1 ? '' : withoutTitle.slice(cut)
    return { title, lead, rest, toc, rows, refs: full.refs }
  }, [article, entries])

  return (
    <article className="wiki-body">
      <div style={{ fontSize: 13, color: '#54595d', marginTop: 4 }}>Материал из Летописи Теслы — отрядной википедии</div>
      <Markdown text={`# ${title}`} tone="light" />
      <Infobox title={title} rows={rows} />
      {lead.trim() && <Markdown text={lead} tone="light" />}
      {toc.length >= 2 && <Toc toc={toc} />}
      {rest.trim() && <Markdown text={rest} tone="light" />}
      {refs.length > 0 && <Notes refs={refs} />}
      <div style={{ marginTop: 24, border: '1px solid #a2a9b1', background: '#f8f9fa', borderRadius: 2, padding: '10px 14px', fontSize: 13, color: '#202122' }}>
        Категории:{' '}
        <a href={`/wiki?cat=${categoryOf(article.slug)}`} style={{ color: '#3366CC', textDecoration: 'none' }}>
          {categoryOf(article.slug)}
        </a>
      </div>
      <div style={{ marginTop: 24 }}>
        <a href="/wiki" style={{ display: 'inline-block', fontSize: 14, fontWeight: 700, color: '#fff', background: '#7A3EE6', borderRadius: 999, padding: '12px 24px', textDecoration: 'none' }}>
          ← Все статьи
        </a>
      </div>
      <style>{'@media (max-width: 720px) { .wiki-infobox { float: none !important; width: auto !important; margin: 16px 0 !important; } } .wiki-body a:hover { text-decoration: underline; }'}</style>
    </article>
  )
}

/** Карточка справа: мета-буллиты из начала статьи (ссылки работают, цитаты вырезаны). */
function Infobox({ title, rows }: { title: string; rows: InfoRow[] }): React.JSX.Element | null {
  if (rows.length === 0) return null
  return (
    <aside role="complementary" aria-label="Карточка статьи" className="wiki-infobox" style={{ float: 'right', clear: 'right', width: 290, margin: '6px 0 16px 20px', border: '1px solid #a2a9b1', background: '#f8f9fa', fontSize: 13, lineHeight: 1.5 }}>
      <div style={{ background: '#ede9fe', borderBottom: '1px solid #a2a9b1', padding: '8px 12px', fontWeight: 700, fontSize: 14, color: '#202122', textAlign: 'center' }}>
        {title}
      </div>
      <table style={{ borderCollapse: 'collapse', width: '100%' }}>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} style={{ borderTop: i === 0 ? 'none' : '1px solid #eaecf0' }}>
              <th scope="row" style={{ textAlign: 'left', verticalAlign: 'top', padding: '7px 8px 7px 12px', color: '#202122', fontWeight: 700, width: '38%' }}>
                {r.k}
              </th>
              <td style={{ verticalAlign: 'top', padding: '7px 12px 7px 4px', color: '#202122' }}>
                <Markdown text={wikiLinksToMd(stripCites(r.v)) || '—'} tone="light" />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </aside>
  )
}

/** Содержание: якоря на разделы. */
function Toc({ toc }: { toc: TocEntry[] }): React.JSX.Element {
  return (
    <nav aria-label="Содержание" style={{ display: 'inline-block', minWidth: 220, border: '1px solid #a2a9b1', background: '#f8f9fa', padding: '10px 16px', margin: '8px 0', fontSize: 13 }}>
      <div style={{ fontWeight: 700, color: '#202122', marginBottom: 6 }}>Содержание</div>
      <ol style={{ margin: 0, paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 3 }}>
        {toc.map((t, i) => (
          <li key={t.id}>
            <a href={`#${t.id}`} style={{ color: '#3366CC', textDecoration: 'none' }}>
              {i + 1} {t.text}
            </a>
          </li>
        ))}
      </ol>
    </nav>
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
    <div>
      <a href="/wiki" style={{ fontSize: 13, color: '#3366CC', textDecoration: 'none' }}>
        ← Все статьи
      </a>
      {loading && <div style={{ marginTop: 24, color: '#6F6459', fontSize: 15 }}>Открываем статью…</div>}
      {!loading && missing && <div style={{ marginTop: 24, color: '#B3261E', fontSize: 15 }}>Такой статьи в Летописи нет.</div>}
      {!loading && article && <ArticleView article={article} entries={entries} />}
    </div>
  )
}
