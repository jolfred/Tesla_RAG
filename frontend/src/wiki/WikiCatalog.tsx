import React, { useEffect, useMemo, useState } from 'react'

import { api } from '../api/client'
import type { WikiNode } from '../types'
import { categoryOf } from './wikilinks'

/** Каталог Летописи: /wiki. Строки — настоящие ссылки на страницы статей. */
export default function WikiCatalog(): React.JSX.Element {
  const [pages, setPages] = useState<WikiNode[]>([])
  const [failed, setFailed] = useState(false)
  const [query, setQuery] = useState('')
  const [cat, setCat] = useState<string>('all')

  useEffect(() => {
    let alive = true
    api
      .wikiPages()
      .then((p) => {
        if (alive) setPages(p.pages ?? [])
      })
      .catch(() => {
        if (alive) setFailed(true)
      })
    return () => {
      alive = false
    }
  }, [])

  const cats = useMemo(() => {
    const m = new Map<string, number>()
    for (const p of pages) {
      const c = categoryOf(p.kind)
      m.set(c, (m.get(c) ?? 0) + 1)
    }
    return [...m.entries()].sort((a, b) => b[1] - a[1])
  }, [pages])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    let list = pages.filter((p) => cat === 'all' || categoryOf(p.kind) === cat)
    if (q) list = list.filter((p) => p.title.toLowerCase().includes(q) || p.slug.includes(q))
    return list.slice(0, 80)
  }, [pages, query, cat])

  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '40px 20px 80px' }}>
      <div style={{ fontSize: 12, fontWeight: 800, letterSpacing: '0.14em', textTransform: 'uppercase', color: '#6D28D9' }}>
        Летопись
      </div>
      <h1 className="tesla-display" style={{ fontSize: 'clamp(30px, 5vw, 46px)', lineHeight: 1.1, margin: '10px 0 0', color: '#211B16' }}>
        Отрядная википедия Теслы
      </h1>
      <p style={{ color: '#6F6459', fontSize: 16, lineHeight: 1.65, margin: '12px 0 0', maxWidth: '60ch' }}>
        {pages.length > 0 ? `${pages.length} статей: отряды, люди, события и традиции штаба.` : 'Статьи штаба, люди и события.'}
      </p>

      {failed ? (
        <div style={{ marginTop: 24, background: '#fff', border: '1px solid #E7DFD2', borderRadius: 16, padding: 22, color: '#B3261E', fontSize: 14 }}>
          Не удалось загрузить Летопись. Проверь соединение и обнови страницу.
        </div>
      ) : (
        <>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Найти статью: отряд, человек, событие…"
            aria-label="Найти статью Летописи"
            style={{ width: '100%', boxSizing: 'border-box', marginTop: 24, background: '#fff', border: '1px solid #E7DFD2', borderRadius: 14, padding: '13px 16px', color: '#211B16', fontSize: 15, outline: 'none' }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 12, flexWrap: 'wrap' }}>
            {[{ k: 'all', n: pages.length }, ...cats.map(([k, n]) => ({ k, n }))].map(({ k, n }) => (
              <button
                key={k}
                type="button"
                onClick={() => setCat(k)}
                style={{
                  fontSize: 13,
                  fontWeight: 700,
                  borderRadius: 999,
                  padding: '7px 14px',
                  cursor: 'pointer',
                  border: cat === k ? '1px solid #6D28D9' : '1px solid #E7DFD2',
                  background: cat === k ? '#F1EAFE' : '#fff',
                  color: cat === k ? '#6D28D9' : '#6F6459',
                }}
              >
                {k === 'all' ? 'Все' : k} · {n}
              </button>
            ))}
          </div>

          <ul aria-label="Каталог статей" style={{ listStyle: 'none', margin: '20px 0 0', padding: 0, background: '#fff', border: '1px solid #E7DFD2', borderRadius: 18, overflow: 'hidden' }}>
            {results.map((p, idx) => (
              <li key={p.slug} style={{ borderTop: idx === 0 ? 'none' : '1px solid #EFE9DD' }}>
                <a
                  href={`/wiki/${p.slug}`}
                  style={{ display: 'flex', alignItems: 'baseline', gap: 12, padding: '14px 20px', textDecoration: 'none' }}
                >
                  <span style={{ fontSize: 11, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.08em', color: '#6D28D9', whiteSpace: 'nowrap' }}>
                    {categoryOf(p.kind)}
                  </span>
                  <span style={{ fontSize: 16, fontWeight: 600, color: '#211B16' }}>{p.title}</span>
                  <span style={{ marginLeft: 'auto', color: '#ABA094', fontSize: 13, fontFamily: 'JetBrains Mono, ui-monospace, monospace' }}>{p.slug}</span>
                </a>
              </li>
            ))}
          </ul>
          {results.length === 0 && <div style={{ padding: 24, fontSize: 14, color: '#6F6459' }}>Ничего не найдено — попробуй другой запрос.</div>}
        </>
      )}
    </div>
  )
}
