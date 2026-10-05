import React, { useEffect, useMemo, useState } from 'react'

import { adminApi } from './adminClient'
import { categoryName } from '../wiki/wikilinks'

interface WikiGraph {
  nodes: { slug: string; title: string; kind: string }[]
  edges: { source: string; target: string }[]
}

const KIND_COLORS: Record<string, string> = {
  person: '#2563eb', squad: '#16a34a', project: '#9333ea', event: '#dc2626',
  heritage: '#ca8a04', methodology: '#0891b2', hq: '#ea580c',
}

/** Связи Wiki из того же endpoint, которым питается публичная Летопись. */
export default function WikiGraphTab(): React.JSX.Element {
  const [data, setData] = useState<WikiGraph | null>(null)
  const [query, setQuery] = useState('')
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')

  useEffect(() => {
    let alive = true
    adminApi.graphExport()
      .then((graph) => { if (alive) setData(graph) })
      .catch((e: unknown) => { if (alive) setErr(e instanceof Error ? e.message : 'Не удалось загрузить граф Летописи') })
      .finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [])

  const filtered = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('ru')
    return (data?.nodes ?? []).filter((node) => !q || node.title.toLocaleLowerCase('ru').includes(q) || node.slug.toLowerCase().includes(q))
  }, [data, query])

  const mapNodes = filtered.slice(0, 120)
  const ids = new Set(mapNodes.map((node) => node.slug))
  const positions = new Map<string, { x: number; y: number }>()
  mapNodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / Math.max(mapNodes.length, 1)
    positions.set(node.slug, { x: 260 + 220 * Math.cos(angle), y: 260 + 220 * Math.sin(angle) })
  })
  const edges = (data?.edges ?? []).filter((edge) => ids.has(edge.source) && ids.has(edge.target)).slice(0, 300)

  return (
    <div>
      <div className="ta-card">
        <p className="ta-muted" style={{ marginTop: 0 }}>
          Граф страниц Летописи: узлы — статьи, линии — ссылки между ними. Данные загружаются из Wiki API; граф Neo4j здесь не используется.
        </p>
        <input className="ta-input" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Найти статью…" aria-label="Найти статью в графе Летописи" />
        {err && <p className="ta-error">{err}</p>}
        {loading && <p className="ta-muted">Загрузка графа Летописи…</p>}
        {data && <p className="ta-muted" style={{ marginBottom: 0 }}>{data.nodes.length} статей · {data.edges.length} ссылок</p>}
      </div>

      {data && (
        <div className="ta-card">
          {mapNodes.length > 0 ? (
            <>
              <p className="ta-muted" style={{ marginTop: 0 }}>
                На схеме первые {mapNodes.length} из {filtered.length} совпавших статей; показано до {edges.length} связей.
              </p>
              <svg viewBox="0 0 520 520" role="img" aria-label="Граф статей Летописи" style={{ width: '100%', maxWidth: 640 }}>
                {edges.map((edge, i) => {
                  const a = positions.get(edge.source)
                  const b = positions.get(edge.target)
                  return a && b ? <line key={`${edge.source}:${edge.target}:${i}`} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#d1d5db" strokeWidth={1} /> : null
                })}
                {mapNodes.map((node, i) => {
                  const p = positions.get(node.slug)
                  if (!p) return null
                  return <a key={node.slug} href={`/wiki/${node.slug}`}>
                    <g>
                      <circle cx={p.x} cy={p.y} r={8} fill={KIND_COLORS[node.kind] ?? '#6b7280'}>
                        <title>{node.title} · {categoryName(node.kind)}</title>
                      </circle>
                      {i % 3 === 0 && <text x={p.x + 11} y={p.y + 4} fontSize={9} fill="#374151">{node.title.slice(0, 22)}</text>}
                    </g>
                  </a>
                })}
              </svg>
            </>
          ) : <p className="ta-muted">Под этот запрос статьи не найдены.</p>}
          <ul aria-label="Статьи в графе" style={{ columns: 2, paddingLeft: 20 }}>
            {filtered.map((node) => <li key={node.slug}><a href={`/wiki/${node.slug}`}>{node.title}</a> <span className="ta-muted">· {categoryName(node.kind)}</span></li>)}
          </ul>
        </div>
      )}
    </div>
  )
}
