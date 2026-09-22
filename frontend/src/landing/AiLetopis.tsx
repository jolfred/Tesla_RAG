import React, { useState } from 'react'
import { motion } from 'framer-motion'

import { api } from '../api/client'
import type { ChatResponse } from '../types'
import { Markdown } from '../wiki/markdown'
import { PRESET_QUESTIONS } from './data'

interface AnswerState {
  question: string
  loading: boolean
  data: ChatResponse | null
  error: string
}

const MODE_LABELS: Record<string, string> = {
  struct: 'Структурный',
  local: 'Локальный',
  global: 'Глобальный',
  basic: 'Базовый',
  wiki: 'По Летописи',
}

/** Карусель превью постов: переключение стрелками, счётчик. */
function PreviewCarousel({ previews }: { previews: NonNullable<ChatResponse['previews']> }): React.JSX.Element | null {
  const [idx, setIdx] = useState(0)
  if (previews.length === 0) return null
  const cur = previews[Math.min(idx, previews.length - 1)]
  const go = (d: number): void => setIdx((i) => (i + d + previews.length) % previews.length)
  const arrow: React.CSSProperties = {
    width: 36,
    height: 36,
    minWidth: 36,
    borderRadius: 999,
    border: '1px solid rgba(157,101,255,0.5)',
    background: 'rgba(122,62,230,0.16)',
    color: '#D9CCFF',
    fontSize: 18,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  }
  return (
    <div style={{ flex: '0 0 300px', alignSelf: 'start', minWidth: 0 }} className="ai-preview-col">
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <button type="button" onClick={() => go(-1)} aria-label="Предыдущий пост" style={arrow}>‹</button>
        <span style={{ fontSize: 12, fontWeight: 700, color: '#9D65FF', whiteSpace: 'nowrap' }}>
          Пост {Math.min(idx, previews.length - 1) + 1} / {previews.length}
        </span>
        <button type="button" onClick={() => go(1)} aria-label="Следующий пост" style={arrow}>›</button>
      </div>
      <VkPreview key={cur.url} preview={cur} />
      <style>{'.ai-preview-col aside { flex: none !important; width: 100%; }'}</style>
    </div>
  )
}

/** Предпросмотр VK-поста: группа, дата, выдержка, фото, кнопка «Открыть в VK». */
function VkPreview({ preview }: { preview: NonNullable<ChatResponse['previews']>[number] }): React.JSX.Element {
  const initial = (preview.group_name || 'Т').trim().charAt(0).toUpperCase()
  return (
    <aside
      className="glass-card"
      style={{ borderRadius: 16, overflow: 'hidden', flex: '0 0 300px', alignSelf: 'start' }}
      aria-label="Предпросмотр поста ВКонтакте"
    >
      <div style={{ display: 'flex', gap: 10, alignItems: 'center', padding: '14px 14px 10px' }}>
        <span
          style={{
            width: 40,
            height: 40,
            minWidth: 40,
            borderRadius: 999,
            background: 'linear-gradient(135deg, #7A3EE6, #9D65FF)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: 16,
          }}
        >
          {initial}
        </span>
        <div style={{ minWidth: 0 }}>
          <div style={{ fontWeight: 700, fontSize: 13.5, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {preview.group_name || 'Штаб Тесла'}
          </div>
          <div style={{ fontSize: 12, color: '#8E86A8' }}>{preview.published_at ? preview.published_at.slice(0, 10) : 'ВКонтакте'}</div>
        </div>
      </div>
      {preview.photo && (
        <img src={preview.photo} alt="Фото из поста" loading="lazy" style={{ width: '100%', maxHeight: 220, objectFit: 'cover', display: 'block' }} />
      )}
      {preview.text && (
        <p style={{ fontSize: 13, lineHeight: 1.55, color: '#CFC6EC', margin: 0, padding: '10px 14px 0' }}>{preview.text}</p>
      )}
      <div style={{ padding: 14 }}>
        <a
          href={preview.url}
          target="_blank"
          rel="noreferrer"
          style={{
            display: 'block',
            textAlign: 'center',
            background: 'rgba(122,62,230,0.18)',
            border: '1px solid rgba(122,62,230,0.45)',
            color: '#D9CCFF',
            fontWeight: 700,
            fontSize: 13.5,
            borderRadius: 12,
            padding: '10px 12px',
            textDecoration: 'none',
          }}
        >
          Открыть пост в VK →
        </a>
      </div>
    </aside>
  )
}

function AnswerCard({ state }: { state: AnswerState }): React.JSX.Element | null {
  if (state.loading) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 12, filter: 'blur(6px)' }}
        animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
        className="glass-card"
        style={{ borderRadius: 20, padding: 20, marginTop: 16, display: 'flex', gap: 12, alignItems: 'center' }}
      >
        <div
          style={{
            width: 36,
            height: 36,
            borderRadius: 999,
            border: '2px solid rgba(122,62,230,0.3)',
            borderTopColor: '#9D65FF',
            animation: 'spin 0.9s linear infinite',
          }}
        />
        <div style={{ fontSize: 14, color: '#CFC6EC' }}>ИИ Летопись листает архив штаба…</div>
        <style>{'@keyframes spin { to { transform: rotate(360deg); } }'}</style>
      </motion.div>
    )
  }
  if (state.error) {
    return (
      <div className="glass-card" style={{ borderRadius: 20, padding: 20, marginTop: 16, color: '#FF9D9D', fontSize: 14 }}>
        {state.error}
      </div>
    )
  }
  if (!state.data) return null
  const d = state.data
  return (
    <motion.div
      initial={{ opacity: 0, y: 16, filter: 'blur(8px)' }}
      animate={{ opacity: 1, y: 0, filter: 'blur(0px)' }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      className="glass-card"
      style={{ borderRadius: 20, marginTop: 16, overflow: 'hidden' }}
    >
      <div style={{ padding: 20 }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              background: '#7A3EE6',
              borderRadius: 999,
              padding: '5px 10px',
            }}
          >
            ИИ Летопись
          </span>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              border: '1px solid rgba(157,101,255,0.5)',
              color: '#D9CCFF',
              borderRadius: 999,
              padding: '5px 10px',
              background: 'rgba(7,6,10,0.6)',
            }}
          >
            {MODE_LABELS[d.mode] ?? d.mode} · {d.posts_used} пост(ов) · {d.facts_count} факт(ов)
          </span>
        </div>
        <div className="ai-answer-cols" style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
          <div style={{ flex: '1 1 auto', minWidth: 0 }}>
            <div style={{ fontSize: 12, color: '#9D65FF', fontWeight: 700, marginBottom: 6, letterSpacing: '0.04em' }}>
              ВЫДЕРЖКА ИЗ БАЗЫ ШТАБА
            </div>
            <div style={{ textAlign: 'left' }}>
              <Markdown text={d.answer} tone="dark" />
            </div>
          </div>
          {(d.previews ?? []).length > 0 && (
            <PreviewCarousel key={(d.previews ?? []).map((p) => p.url).join('|')} previews={d.previews ?? []} />
          )}
        </div>
      </div>
      <style>{'@media (max-width: 760px) { .ai-answer-cols { flex-direction: column !important; } .ai-preview-col { flex: none !important; width: 100%; } }'}</style>
    </motion.div>
  )
}

export default function AiLetopis(): React.JSX.Element {
  const [input, setInput] = useState('')
  const [state, setState] = useState<AnswerState>({ question: '', loading: false, data: null, error: '' })

  const ask = async (question: string): Promise<void> => {
    const q = question.trim()
    if (!q || state.loading) return
    setState((s) => ({ ...s, question: q, loading: true, data: null, error: '' }))
    try {
      const resp = await api.chat({ question: q })
      setState((s) => ({ ...s, loading: false, data: resp }))
    } catch {
      setState((s) => ({ ...s, loading: false, error: 'Не удалось связаться с архивом. Проверь соединение и попробуй ещё раз.' }))
    }
  }

  return (
    <div style={{ width: '100%', maxWidth: 780, margin: '28px auto 0' }}>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          void ask(input)
        }}
        className="hero-glow-input"
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          background: 'rgba(17,15,24,0.82)',
          backdropFilter: 'blur(18px)',
          borderRadius: 20,
          padding: '8px 8px 8px 20px',
          border: '1px solid rgba(122,62,230,0.55)',
        }}
      >
        <span style={{ color: '#9D65FF', fontSize: 18 }}>✦</span>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Спроси ИИ Летопись Теслы..."
          aria-label="Спроси ИИ Летопись Теслы"
          style={{
            flex: 1,
            background: 'transparent',
            border: 'none',
            outline: 'none',
            color: '#fff',
            fontSize: 16,
            padding: '12px 4px',
            minWidth: 0,
          }}
        />
        <button
          type="submit"
          disabled={!input.trim() || state.loading}
          style={{
            background: input.trim() ? '#7A3EE6' : 'rgba(122,62,230,0.35)',
            color: '#fff',
            border: 'none',
            borderRadius: 14,
            padding: '12px 20px',
            fontWeight: 700,
            fontSize: 14,
            cursor: input.trim() ? 'pointer' : 'default',
            transition: 'background 0.2s',
            whiteSpace: 'nowrap',
          }}
          onMouseEnter={(e) => {
            if (input.trim()) (e.currentTarget as HTMLButtonElement).style.background = '#9D65FF'
          }}
          onMouseLeave={(e) => {
            if (input.trim()) (e.currentTarget as HTMLButtonElement).style.background = '#7A3EE6'
          }}
        >
          {state.loading ? '···' : 'Спросить →'}
        </button>
      </form>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10, marginTop: 14 }}>
        {PRESET_QUESTIONS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => {
              setInput(p.question)
              void ask(p.question)
            }}
            className="glass-card"
            style={{
              borderRadius: 16,
              padding: '13px 14px',
              textAlign: 'left',
              color: '#EAE4FF',
              fontSize: 13.5,
              fontWeight: 600,
              cursor: 'pointer',
              background: 'rgba(17,15,24,0.6)',
            }}
          >
            <span style={{ color: '#9D65FF', marginRight: 6 }}>◆</span>
            {p.label}
          </button>
        ))}
      </div>
      <style>{'@media (max-width: 560px) { div[style*="repeat(2"] { grid-template-columns: 1fr !important; } }'}</style>

      <AnswerCard state={state} />
    </div>
  )
}
