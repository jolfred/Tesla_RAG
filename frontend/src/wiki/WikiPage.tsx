import React, { useEffect, useState } from 'react'

import { api } from '../api/client'
import teslaFavicon from '../assets/logos/tesla.jpg'
import WikiArticle from './WikiArticle'
import WikiCatalog from './WikiCatalog'
import { categoryOf } from './wikilinks'

/** Поиск в шапке -> каталог с ?q=. */
function SearchBox(): React.JSX.Element {
  const [q, setQ] = useState('')
  return (
    <form
      role="search"
      style={{ display: 'flex', flex: '1 1 auto', maxWidth: 420, minWidth: 140 }}
      onSubmit={(e) => {
        e.preventDefault()
        window.location.href = `/wiki${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ''}`
      }}
    >
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Поиск по Летописи"
        aria-label="Поиск по Летописи"
        style={{ flex: 1, minWidth: 0, border: '1px solid #a2a9b1', borderRight: 'none', borderRadius: '2px 0 0 2px', padding: '7px 10px', fontSize: 14, outline: 'none', color: '#202122' }}
      />
      <button type="submit" style={{ border: '1px solid #a2a9b1', borderRadius: '0 2px 2px 0', background: '#f8f9fa', padding: '7px 14px', fontSize: 14, cursor: 'pointer', color: '#202122' }}>
        Найти
      </button>
    </form>
  )
}

/** Сайдбар: навигация, случайная статья, категории. */
function Sidebar(): React.JSX.Element {
  const [cats, setCats] = useState<[string, number][]>([])
  useEffect(() => {
    let alive = true
    api
      .wikiPages()
      .then((p) => {
        if (!alive) return
        const m = new Map<string, number>()
        for (const n of p.pages ?? []) {
          const c = categoryOf(n.kind)
          m.set(c, (m.get(c) ?? 0) + 1)
        }
        setCats([...m.entries()].sort((a, b) => b[1] - a[1]))
      })
      .catch(() => {
        /* без каталога — только статичная навигация */
      })
    return () => {
      alive = false
    }
  }, [])

  const random = (): void => {
    api
      .wikiPages()
      .then((p) => {
        const list = p.pages ?? []
        if (list.length > 0) window.location.href = `/wiki/${list[Math.floor(Math.random() * list.length)].slug}`
      })
      .catch(() => undefined)
  }

  const link: React.CSSProperties = { color: '#3366CC', textDecoration: 'none', fontSize: 13 }
  const head: React.CSSProperties = { fontSize: 12, color: '#54595d', borderBottom: '1px solid #c8ccd1', paddingBottom: 4, margin: '16px 0 8px' }
  return (
    <nav aria-label="Навигация Летописи" className="wiki-sidebar" style={{ fontSize: 13 }}>
      <div style={head}>Навигация</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <a href="/wiki" style={link}>Заглавная страница</a>
        <button type="button" onClick={random} style={{ ...link, background: 'none', border: 'none', padding: 0, cursor: 'pointer', textAlign: 'left', font: 'inherit' }}>
          Случайная статья
        </button>
        <a href="/" style={link}>Штаб Тесла — на главную</a>
      </div>
      {cats.length > 0 && (
        <>
          <div style={head}>Категории</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {cats.map(([c, n]) => (
              <a key={c} href={`/wiki?cat=${c}`} style={link}>
                {c} · {n}
              </a>
            ))}
          </div>
        </>
      )}
    </nav>
  )
}

/** Отдельная страница вики: /wiki — каталог, /wiki/<slug> — статья. */
export default function WikiPage(): React.JSX.Element {
  const m = window.location.pathname.match(/^\/wiki\/(.+?)\/?$/)
  const slug = m ? decodeURIComponent(m[1]) : ''
  return (
    <div style={{ background: '#f8f9fa', minHeight: '100vh', color: '#202122' }}>
      <header style={{ background: '#fff', borderBottom: '1px solid #a2a9b1' }}>
        <div style={{ maxWidth: 1120, margin: '0 auto', padding: '10px 20px', display: 'flex', alignItems: 'center', gap: 14, flexWrap: 'wrap' }}>
          <a href="/wiki" style={{ display: 'flex', alignItems: 'center', gap: 10, textDecoration: 'none' }}>
            <img src={teslaFavicon} alt="Логотип штаба Тесла" width={40} height={40} style={{ width: 40, height: 40, borderRadius: 8, objectFit: 'cover' }} />
            <span style={{ fontFamily: "'PT Serif', Georgia, serif", fontSize: 20, color: '#202122' }}>Летопись Теслы</span>
          </a>
          <SearchBox />
        </div>
      </header>
      <div className="wiki-cols" style={{ maxWidth: 1120, margin: '0 auto', padding: '0 20px', display: 'grid', gridTemplateColumns: '190px 1fr', gap: 28, alignItems: 'start' }}>
        <div className="wiki-sidecol" style={{ padding: '18px 0 40px' }}>
          <Sidebar />
        </div>
        <main style={{ background: '#fff', borderLeft: '1px solid #a2a9b1', borderRight: '1px solid #a2a9b1', padding: '20px 28px 40px', minHeight: '70vh', minWidth: 0 }}>
          {slug ? <WikiArticle slug={slug} /> : <WikiCatalog />}
        </main>
      </div>
      <footer style={{ maxWidth: 1120, margin: '0 auto', padding: '16px 20px 32px', fontSize: 12, color: '#54595d' }}>
        Летопись Теслы — отрядная википедия штаба СО КГЭУ. Тексты собраны из открытых постов VK; каждый факт — со сноской на источник.
      </footer>
      <style>{'@media (max-width: 860px) { .wiki-cols { grid-template-columns: 1fr !important; gap: 0 !important; } .wiki-sidecol { padding-bottom: 0 !important; } main { border: none !important; padding: 8px 0 32px !important; } }'}</style>
    </div>
  )
}
