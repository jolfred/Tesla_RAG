import React, { useEffect, useState } from 'react'

import { api } from '../api/client'
import type { WikiPageData } from '../types'
import { categoryOf, parseWikiLinks } from './wikilinks'

const INLINE_RE = /(\*\*[^*]+\*\*|\[\[[^\]]+\]\]|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>"'\]]+)/g
const WALL_RE = /wall-?\d+_\d+/

/** wall-ID читателю не нужен — показываем «пост VK». */
function vkLabel(label: string, url: string): string {
  if (WALL_RE.test(label) || WALL_RE.test(url)) return 'пост VK'
  return label.length > 40 ? `${label.slice(0, 40)}…` : label
}

const LINK_STYLE: React.CSSProperties = { color: '#6D28D9', textDecoration: 'underline', textDecorationStyle: 'dotted', textUnderlineOffset: 3 }

/** Инлайн-разметка: жирный, [[вики-ссылки]] (настоящие <a>), [текст](url), голые URL. */
function Inline({ text }: { text: string }): React.JSX.Element {
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
      if (part.type === 'link') {
        out.push(
          <a key={i++} href={`/wiki/${part.slug}`} style={LINK_STYLE}>
            {part.label}
          </a>,
        )
      } else {
        pushText(tok)
      }
    } else {
      const md = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/.exec(tok)
      const url = md ? md[2] : tok
      out.push(
        <a key={i++} href={url} target="_blank" rel="noreferrer" style={LINK_STYLE}>
          {vkLabel(md ? md[1] : tok, url)}
        </a>,
      )
    }
    last = m.index + tok.length
  }
  pushText(text.slice(last))
  return <>{out}</>
}

/** Минимум markdown: заголовки, списки, таблицы, параграфы.
 * Frontmatter и служебный раздел «Источники данных» (локальные пути) вырезаны. */
function Body({ markdown }: { markdown: string }): React.JSX.Element {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, '')
  const lines: string[] = []
  let skip = false
  for (const line of body.split('\n')) {
    const h = /^(#{1,3})\s+(.*)$/.exec(line)
    if (h) skip = h[2].trim().toLowerCase() === 'источники данных'
    if (!skip) lines.push(line)
  }
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
          { key: k++, style: { fontSize: level === 1 ? 24 : 19, margin: '28px 0 10px', lineHeight: 1.3, color: '#211B16' } },
          <Inline text={h[2]} />,
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
          <div key={k++} style={{ overflowX: 'auto', margin: '14px 0', border: '1px solid #E7DFD2', borderRadius: 12 }}>
            <table style={{ borderCollapse: 'collapse', fontSize: 14, width: '100%', background: '#fff' }}>
              <thead>
                <tr style={{ background: '#F6F1E8' }}>
                  {head.map((c, j) => (
                    <th key={j} style={{ textAlign: 'left', padding: '9px 12px', color: '#6D28D9', fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                      <Inline text={c} />
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rest.map((r, ri) => (
                  <tr key={ri} style={{ borderTop: '1px solid #EFE9DD' }}>
                    {r.map((c, j) => (
                      <td key={j} style={{ padding: '9px 12px', color: '#3D352D', verticalAlign: 'top' }}>
                        <Inline text={c} />
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
        <ul key={k++} style={{ margin: '10px 0', paddingLeft: 22, display: 'flex', flexDirection: 'column', gap: 6 }}>
          {items.map((t, j) => (
            <li key={j} style={{ fontSize: 16, lineHeight: 1.7, color: '#3D352D' }}>
              <Inline text={t} />
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
      <p key={k++} style={{ fontSize: 16, lineHeight: 1.75, color: '#3D352D', margin: '10px 0' }}>
        <Inline text={para.join(' ')} />
      </p>,
    )
  }
  return <>{blocks}</>
}

/** Заголовок статьи — первый `# …`; остальное — тело. */
function splitTitle(markdown: string, fallback: string): [string, string] {
  const body = markdown.replace(/^---\n[\s\S]*?\n---\n/, '')
  const m = body.match(/^#\s+(.+?)\s*$/m)
  if (!m) return [fallback, body]
  return [m[1], body.replace(m[0], '')]
}

/** Отдельная страница статьи: /wiki/<slug>. */
export default function WikiArticle({ slug }: { slug: string }): React.JSX.Element {
  const [article, setArticle] = useState<WikiPageData | null>(null)
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
      {!loading && article && <ArticleView article={article} />}
    </div>
  )
}

function ArticleView({ article }: { article: WikiPageData }): React.JSX.Element {
  const [title, rest] = splitTitle(article.markdown, article.slug)
  const shown = article.sources.slice(0, 10)
  const wallCount = shown.filter((x) => WALL_RE.test(x)).length
  return (
    <article>
      <div style={{ marginTop: 16, fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.12em', color: '#6D28D9' }}>
        {categoryOf(article.slug)}
      </div>
      <h1 className="tesla-display" style={{ fontSize: 'clamp(28px, 5vw, 40px)', lineHeight: 1.15, margin: '10px 0 0', color: '#211B16' }}>
        {title}
      </h1>
      <Body markdown={rest} />
      {article.sources.length > 0 && (
        <div style={{ marginTop: 32, borderTop: '1px solid #E7DFD2', paddingTop: 16 }}>
          <div style={{ fontSize: 12, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6D28D9', marginBottom: 10 }}>
            Источники
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {shown.map((u, idx) => {
              const label = WALL_RE.test(u) && wallCount > 1 ? `пост VK · ${idx + 1}` : vkLabel(u, u)
              return (
                <a key={u} href={u} target="_blank" rel="noreferrer" style={{ fontSize: 14, color: '#6D28D9', overflowWrap: 'anywhere' }}>
                  {label}
                </a>
              )
            })}
          </div>
        </div>
      )}
      <div style={{ marginTop: 32 }}>
        <a href="/wiki" style={{ display: 'inline-block', fontSize: 14, fontWeight: 700, color: '#fff', background: '#7A3EE6', borderRadius: 999, padding: '12px 24px', textDecoration: 'none' }}>
          ← Все статьи
        </a>
      </div>
    </article>
  )
}
