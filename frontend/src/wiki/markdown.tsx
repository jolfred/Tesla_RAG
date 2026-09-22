import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { unwrapBracketedUrls } from './footnotes'

/** Общий рендер markdown: статьи Летописи (light) и ответы ИИ (dark). Таблицы — через GFM. */
export function Markdown({ text, tone }: { text: string; tone: 'light' | 'dark' }): React.JSX.Element {
  const ink = tone === 'light' ? '#3D352D' : '#F2EFFF'
  const accent = tone === 'light' ? '#6D28D9' : '#B79CFF'
  const faint = tone === 'light' ? '#6F6459' : '#8E86A8'
  const line = tone === 'light' ? '#E7DFD2' : 'rgba(157,101,255,0.35)'
  const head = tone === 'light' ? '#211B16' : '#FFFFFF'
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a({ href, children }) {
          if (href?.startsWith('#ref-')) {
            const n = href.slice('#ref-'.length)
            return (
              <a id={`fnref-${n}`} href={href} style={{ color: accent, fontSize: '0.78em', fontWeight: 800, verticalAlign: 'super', textDecoration: 'none' }}>
                [{children}]
              </a>
            )
          }
          const internal = href?.startsWith('/wiki/')
          return (
            <a
              href={href}
              {...(internal ? {} : { target: '_blank', rel: 'noreferrer' })}
              style={{ color: accent, overflowWrap: 'anywhere' }}
            >
              {children}
            </a>
          )
        },
        h1({ children }) {
          return <h1 style={{ fontSize: 'clamp(28px, 5vw, 40px)', lineHeight: 1.15, margin: '10px 0 0', color: head }}>{children}</h1>
        },
        h2({ children }) {
          return <h2 style={{ fontSize: 24, margin: '28px 0 10px', lineHeight: 1.3, color: head }}>{children}</h2>
        },
        h3({ children }) {
          return <h3 style={{ fontSize: 19, margin: '24px 0 8px', lineHeight: 1.3, color: head }}>{children}</h3>
        },
        p({ children }) {
          return <p style={{ fontSize: tone === 'light' ? 16 : 15, lineHeight: 1.75, color: ink, margin: '10px 0', overflowWrap: 'break-word' }}>{children}</p>
        },
        ul({ children }) {
          return <ul style={{ margin: '10px 0', paddingLeft: 22, color: ink }}>{children}</ul>
        },
        ol({ children }) {
          return <ol style={{ margin: '10px 0', paddingLeft: 22, color: ink }}>{children}</ol>
        },
        li({ children }) {
          return <li style={{ lineHeight: 1.7, margin: '4px 0' }}>{children}</li>
        },
        table({ children }) {
          return (
            <div style={{ overflowX: 'auto', margin: '14px 0', border: `1px solid ${line}`, borderRadius: 12 }}>
              <table style={{ borderCollapse: 'collapse', fontSize: 14, width: '100%', background: tone === 'light' ? '#fff' : 'transparent' }}>
                {children}
              </table>
            </div>
          )
        },
        th({ children }) {
          return <th style={{ textAlign: 'left', padding: '9px 12px', color: accent, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{children}</th>
        },
        td({ children }) {
          return <td style={{ padding: '9px 12px', color: ink, verticalAlign: 'top', borderTop: `1px solid ${line}` }}>{children}</td>
        },
        code({ children }) {
          return <code style={{ fontFamily: 'JetBrains Mono, ui-monospace, monospace', fontSize: '0.85em', background: tone === 'light' ? '#F1ECE2' : 'rgba(122,62,230,0.2)', borderRadius: 6, padding: '2px 6px', overflowWrap: 'anywhere' }}>{children}</code>
        },
        pre({ children }) {
          return <pre style={{ overflowX: 'auto', background: tone === 'light' ? '#F1ECE2' : 'rgba(0,0,0,0.4)', borderRadius: 12, padding: '12px 14px', fontSize: 13 }}>{children}</pre>
        },
        blockquote({ children }) {
          return <blockquote style={{ borderLeft: `3px solid ${accent}`, margin: '12px 0', padding: '4px 0 4px 14px', color: faint }}>{children}</blockquote>
        },
        hr() {
          return <hr style={{ border: 'none', borderTop: `1px solid ${line}`, margin: '20px 0' }} />
        },
      }}
    >
      {unwrapBracketedUrls(text)}
    </ReactMarkdown>
  )
}
