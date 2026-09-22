import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { WikiNode, WikiPageData } from '../types'
import { categoryOf, parseWikiLinks } from './wikilinks'

const INLINE_RE = /(\*\*[^*]+\*\*|\[\[[^\]]+\]\]|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>"'\]]+)/g

/** Инлайн-разметка: жирный, [[вики-ссылки]], [текст](url), голые URL. */
function Inline({ text, onWikiLink }: { text: string; onWikiLink: (slug: string) => void }): React.JSX.Element {
  const out: React.ReactNode[] = []
  let last = 0
  let m: RegExpExecArray | null
  let i = 0
  INLINE_RE.lastIndex = 0
  const pushText = (t: string): void => {
    if (t) out.push(<React.Fragment key={i++}>{t}</React.Fragment>)
  }
  while ((m = INLINE_RE.exec(text)) !== null) {
    pushText(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('**')) {
      out.push(<strong key={i++}>{tok.slice(2, -2)}</strong>)
    } else if (tok.startsWith('[[')) {
      const [part] = parseWikiLinks(tok)
      if (part.type === 'link' && part.slug && part.label) {
        const slug = part.slug
        out.push(
          <button
            key={i++}
            type="button"
            onClick={() => onWikiLink(slug)}
            style={{ color: '#B79CFF', background: 'none', border: 'none', padding: 0, cursor: 'pointer', font: 'inherit', textDecoration: 'underline', textDecorationStyle: 'dotted' }}
          >
            {part.label}
          </button>,
        )
      } else {
        pushText(tok)
      }
    } else {
      const md = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(tok)
      const url = md ? md[2] : tok
      const label = md ? md[1] : tok.length > 40 ? `${tok.slice(0, 40)}…` : tok
      out.push(
        <a key={i++} href={url} target="_blank" rel="noreferrer" style={{ color: '#B79CFF' }}>
          {label}
        </a>,
      )
    }
    last = m.index + tok.length
  }
  pushText(text.slice(last))
  return <>{out}</>
}

/** Минимум markdown: заголовки, списки, таблицы, параграфы + frontmatter вырезан. */
function Article({ markdown, onWikiLink }: { markdown: string; onWikiLink: (slug: string) => void }): React.JSX.Element {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, '')
  const lines = body.split('\n')
  const blocks: React.ReactNode[] = []
  let i = 0
  let k = 0
  while (i < lines.length) {
    const line = lines[i]
    if (!line.trim()) {
      i++
      continue
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) {
      const level = h[1].length
      blocks.push(
        React.createElement(
          `h${Math.min(3, level + 1)}` as 'h2',
          { key: k++, style: { fontSize: level === 1 ? 24 : 17, margin: '18px 0 8px', lineHeight: 1.3 } },
          <Inline text={h[2]} onWikiLink={onWikiLink} />,
        ),
      )
      i++
      continue
    }
    if (/^\|.*\|\s*$/.test(line)) {
      const rows: string[][] = []
      while (i < lines.length && /^\|.*\|\s*$/.test(lines[i])) {
        const cells = lines[i].trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim())
        if (!/^:?-+:?$/.test(cells[0].replace(/\s/g, ''))) rows.push(cells)
        i++
      }
      if (rows.length) {
        const [head, ...rest] = rows
        blocks.push(
          <div key={k++} style={{ overflowX: 'auto', margin: '10px 0' }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 13, width: '100%' }}>
              <thead>
                <tr>
                  {head.map((c, j) => (
                    <th key={j} style={{ textAlign: 'left', padding: '6px 8px', color: '#9D65FF', borderBottom: '1px solid rgba(157,101,255,0.4)', fontSize: 12 }}>
                      <Inline text={c} onWikiLink={onWikiLink} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rest.map((r, ri) => (
                  <tr key={ri}>
                    {r.map((c, j) => (
                      <td key={j} style={{ padding: '6px 8px', borderBottom: '1px solid rgba(255,255,255,0.07)', color: '#CFC6EC', verticalAlign: 'top' }}>
                        <Inline text={c} onWikiLink={onWikiLink} />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        )
      }
      continue
    }
    if (/^\s*[-*]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\s*[-*]\s+/, ''))
        i++
      }
      blocks.push(
        <ul key={k++} style={{ margin: '8px 0', paddingLeft: 20, display: 'flex', flexDirection: 'column', gap: 5 }}>
          {items.map((t, j) => (
            <li key={j} style={{ fontSize: 14, lineHeight: 1.6, color: '#EAE4FF' }}>
              <Inline text={t} onWikiLink={onWikiLink} />
            </li>
          ))}
        </ul>,
      )
      continue
    }
    const para: string[] = []
    while (i < lines.length && lines[i].trim() && !/^(#{1,3}\s|[-*]\s+\|)/.test(lines[i])) {
      para.push(lines[i])
      i++
    }
    blocks.push(
      <p key={k++} style={{ fontSize: 14, lineHeight: 1.7, color: '#EAE4FF', margin: '8px 0' }}>
        <Inline text={para.join(' ')} onWikiLink={onWikiLink} />
      </p>,
    )
  }
  return <>{blocks}</>
}

/** Секция «Летопись Теслы»: поиск + каталог + читалка статей. */
export default function WikiSection(): React.JSX.Element {
  const [pages, setPages] = useState<WikiNode[]>([])
  const [failed, setFailed] = useState(false)
  const [query, setQuery] = useState('')
  const [cat, setCat] = useState<string>('all')
  const [slug, setSlug] = useState<string | null>(null)
  const [article, setArticle] = useState<WikiPageData | null>(null)
  const [articleLoading, setArticleLoading] = useState(false)

  useEffect(() => {
    let alive = true
    api
      .wikiPages()
      .then((p) => {
        if (!alive) return
        setPages(p.pages ?? [])
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [])

  const open = (s: string): void => {
    setSlug(s)
    setArticle(null)
    setArticleLoading(true)
    api
      .wikiPage(s)
      .then((a) => {
        setArticle(a)
        setArticleLoading(false)
      })
      .catch(() => setArticleLoading(false))
  }

  const cats = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of pages) m.set(categoryOf(p.kind), (m.get(categoryOf(p.kind)) ?? 0) + 1)
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [pages])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = pages.filter((p) => cat === 'all' || categoryOf(p.kind) === cat)
    if (q) list = list.filter((p) => p.title.toLowerCase().includes(q) || p.slug.includes(q))
    return list.slice(0, 60)
  }, [pages, query, cat])

  return (
    <section aria-label="Летопись Теслы — отрядная википедия" style={{ maxWidth: 1120, margin: '0 auto', padding: '84px 20px 12px' }}>
      <div style={{ maxWidth: 760 }}>
        <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#9D65FF', marginBottom: 10 }}>
          Летопись
        </div>
        <h2 className="tesla-display" style={{ fontSize: 'clamp(26px, 4vw, 40px)', lineHeight: 1.12, margin: 0 }}>
          Летопись Теслы — отрядная википедия
        </h2>
        <p style={{ color: '#B9B0D6', fontSize: 15, lineHeight: 1.65, marginTop: 10 }}>
          {pages.length > 0 ? `${pages.length} статей штаба, люди и события` : 'Статьи штаба, люди и события'} — поиск и тексты из архива.
        </p>
      </div>

      {failed ? (
        <div className="glass-card" style={{ borderRadius: 20, padding: 22, marginTop: 24, color: '#FF9D9D', fontSize: 14 }}>
          Не удалось загрузить Летопись. Проверь соединение и обнови страницу.
        </div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: 10, marginTop: 18, flexWrap: 'wrap' }}>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Найти статью: отряд, человек, событие…"
              aria-label="Найти статью Летописи"
              style={{ flex: '1 1 240px', background: 'rgba(17,15,24,0.82)', border: '1px solid rgba(122,62,230,0.4)', borderRadius: 14, padding: '12px 16px', color: '#fff', fontSize: 14, outline: 'none', minWidth: 0 }}
            />
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {[{ k: 'all', n: pages.length }, ...cats.map(([k, n]) => ({ k, n }))].map(({ k, n }) => (
              <button
                key={k}
                type="button"
                onClick={() => setCat(k)}
                style={{
                  fontSize: 12.5,
                  fontWeight: 700,
                  borderRadius: 999,
                  padding: '7px 13px',
                  cursor: 'pointer',
                  border: cat === k ? '1px solid #9D65FF' : '1px solid rgba(255,255,255,0.14)',
                  background: cat === k ? 'rgba(122,62,230,0.25)' : 'transparent',
                  color: cat === k ? '#fff' : '#B9B0D6',
                }}
              >
                {k === 'all' ? 'Все' : k} · {n}
              </button>
            ))}
          </div>

          <div className="wiki-cols" style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: 14, marginTop: 16, alignItems: 'start' }}>
            <div className="glass-card" style={{ borderRadius: 18, padding: 10, maxHeight: 560, overflowY: 'auto' }} aria-label="Каталог статей">
              {results.map((p) => (
                <button
                  key={p.slug}
                  type="button"
                  onClick={() => open(p.slug)}
                  style={{
                    display: 'block',
                    width: '100%',
                    textAlign: 'left',
                    border: 'none',
                    borderRadius: 12,
                    padding: '9px 12px',
                    cursor: 'pointer',
                    background: slug === p.slug ? 'rgba(122,62,230,0.25)' : 'transparent',
                    color: '#EAE4FF',
                  }}
                >
                  <span style={{ fontSize: 10, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#9D65FF' }}>{categoryOf(p.kind)}</span>
                  <span style={{ display: 'block', fontSize: 14, fontWeight: 600, marginTop: 2 }}>{p.title}</span>
                </button>
              ))}
              {results.length === 0 && <div style={{ padding: 16, fontSize: 13.5, color: '#8E86A8' }}>Ничего не найдено — попробуй другой запрос.</div>}
            </div>

            <div className="glass-card" style={{ borderRadius: 18, padding: 'clamp(18px, 3vw, 32px)', minHeight: 300 }} aria-label="Статья Летописи" aria-live="polite">
              {articleLoading && <div style={{ color: '#8E86A8', fontSize: 14 }}>Открываем статью…</div>}
              {!articleLoading && article && (
                <>
                  <Article markdown={article.markdown} onWikiLink={open} />
                  {article.sources.length > 0 && (
                    <div style={{ marginTop: 18, borderTop: '1px solid rgba(122,62,230,0.25)', paddingTop: 12 }}>
                      <div style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#9D65FF', marginBottom: 8 }}>Источники</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                        {article.sources.slice(0, 10).map((u) => (
                          <a key={u} href={u} target="_blank" rel="noreferrer" style={{ fontSize: 12.5, color: '#B79CFF', overflowWrap: 'anywhere' }}>{u}</a>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              )}
              {!articleLoading && !article && (
                <div style={{ color: '#8E86A8', fontSize: 14, lineHeight: 1.6 }}>
                  Выбери статью в каталоге — текст откроется здесь. Пунктирные ссылки внутри статей ведут на связанные страницы.
                </div>
              )}
            </div>
          </div>
          <style>{'@media (max-width: 860px) { .wiki-cols { grid-template-columns: 1fr !important; } }'}</style>
        </>
      )}
    </section>
  )
}
