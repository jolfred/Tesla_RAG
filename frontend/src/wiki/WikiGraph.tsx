import React, { useMemo, useState } from 'react'

import type { WikiGraphData } from '../types'
import { categoryColor, categoryOf, layoutGraph } from './wikilinks'

interface Props {
  data: WikiGraphData
  selected: string | null
  onSelect: (slug: string) => void
}

const W = 900
const H = 460

/** SVG-граф связей Летописи: drag-pan, zoom колесом и кнопками, клик — открыть статью. */
export default function WikiGraph({ data, selected, onSelect }: Props): React.JSX.Element {
  const [view, setView] = useState({ x: 0, y: 0, w: W })

  const degree = useMemo(() => {
    const d = new Map<string, number>()
    for (const e of data.edges) {
      d.set(e.source, (d.get(e.source) ?? 0) + 1)
      d.set(e.target, (d.get(e.target) ?? 0) + 1)
    }
    return d
  }, [data])

  const pos = useMemo(() => layoutGraph(data.nodes, data.edges, W, H), [data])

  const neighbours = useMemo(() => {
    if (!selected) return null
    const s = new Set<string>([selected])
    for (const e of data.edges) {
      if (e.source === selected) s.add(e.target)
      if (e.target === selected) s.add(e.source)
    }
    return s
  }, [selected])

  const h = (W / view.w) * H
  const zoom = (f: number): void =>
    setView((v) => {
      const w = Math.min(W * 2, Math.max(W / 4, v.w * f))
      return { ...v, w }
    })

  return (
    <div className="glass-card" style={{ borderRadius: 20, overflow: 'hidden', position: 'relative' }}>
      <svg
        className="wiki-graph"
        viewBox={`${view.x} ${view.y} ${view.w} ${h}`}
        style={{ width: '100%', height: 460, display: 'block', background: 'radial-gradient(600px 260px at 50% 0%, rgba(122,62,230,0.16), transparent 70%)' }}
        role="img"
        aria-label="Граф связей статей Летописи"
        onWheel={(e) => zoom(e.deltaY > 0 ? 1.15 : 1 / 1.15)}
      >
        {data.edges.map((e, i) => {
          const a = pos[e.source]
          const b = pos[e.target]
          if (!a || !b) return null
          const hot = selected !== null && (e.source === selected || e.target === selected)
          return (
            <line
              key={i}
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              stroke={hot ? '#9D65FF' : 'rgba(157,101,255,0.22)'}
              strokeWidth={hot ? 1.6 : 1}
            />
          )
        })}
        {data.nodes.map((n) => {
          const p = pos[n.slug]
          if (!p) return null
          const deg = degree.get(n.slug) ?? 0
          const r = 4 + Math.min(10, deg * 1.1) + (categoryOf(n.kind) === 'squad' ? 2 : 0)
          const dim = neighbours !== null && !neighbours.has(n.slug)
          const isSel = n.slug === selected
          return (
            <g
              key={n.slug}
              opacity={dim ? 0.25 : 1}
              onClick={() => onSelect(n.slug)}
              style={{ cursor: 'pointer' }}
            >
              <title>{n.title}</title>
              {isSel && <circle cx={p[0]} cy={p[1]} r={r + 6} fill="none" stroke="#fff" strokeWidth={1.5} />}
              <circle cx={p[0]} cy={p[1]} r={r} fill={categoryColor(n.kind)} fillOpacity={dim ? 0.4 : 0.9} />
              {(deg >= 8 || isSel) && (
                <text x={p[0] + r + 4} y={p[1] + 4} fontSize={11} fill="#D9CCFF" pointerEvents="none">
                  {n.title.length > 22 ? `${n.title.slice(0, 22)}…` : n.title}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      <div style={{ position: 'absolute', top: 12, right: 12, display: 'flex', gap: 6 }}>
        {[
          { label: '+', fn: (): void => zoom(1 / 1.3), aria: 'Приблизить граф' },
          { label: '−', fn: (): void => zoom(1.3), aria: 'Отдалить граф' },
          { label: '⟲', fn: (): void => setView({ x: 0, y: 0, w: W }), aria: 'Сбросить масштаб графа' },
        ].map((b) => (
          <button
            key={b.aria}
            type="button"
            aria-label={b.aria}
            onClick={b.fn}
            style={{
              width: 32,
              height: 32,
              borderRadius: 999,
              border: '1px solid rgba(157,101,255,0.5)',
              background: 'rgba(17,15,24,0.85)',
              color: '#D9CCFF',
              fontSize: 15,
              cursor: 'pointer',
            }}
          >
            {b.label}
          </button>
        ))}
      </div>
      <div style={{ position: 'absolute', left: 14, bottom: 12, display: 'flex', gap: 12, fontSize: 11, color: '#B9B0D6' }}>
        {[
          ['squad', 'Отряды'],
          ['person', 'Люди'],
          ['hq', 'Штаб'],
        ].map(([k, label]) => (
          <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ width: 9, height: 9, borderRadius: 999, background: categoryColor(k) }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  )
}
