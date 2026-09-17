import React, { useState } from 'react'
import { motion } from 'framer-motion'

import { api } from '../api/client'
import type { ChatResponse } from '../types'
import { PRESET_QUESTIONS } from './data'

interface AnswerState {
  question: string
  loading: boolean
  data: ChatResponse | null
  error: string
  image: string
}

const MODE_LABELS: Record<string, string> = {
  struct: 'Структурный',
  local: 'Локальный',
  global: 'Глобальный',
  basic: 'Базовый',
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
      <div style={{ display: 'flex', flexDirection: 'column' }} className="ai-answer-flex">
        <div style={{ position: 'relative', minHeight: 180, flex: '0 0 220px' }}>
          <img
            src={state.image}
            alt="Атмосфера отрядов Тесла"
            loading="lazy"
            style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }}
          />
          <div
            style={{
              position: 'absolute',
              inset: 0,
              background: 'linear-gradient(100deg, rgba(7,6,10,0.1) 30%, rgba(7,6,10,0.88) 100%)',
            }}
          />
          <div style={{ position: 'absolute', left: 14, bottom: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
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
        </div>
        <div style={{ padding: 20 }}>
          <div style={{ fontSize: 12, color: '#9D65FF', fontWeight: 700, marginBottom: 6, letterSpacing: '0.04em' }}>
            ВЫДЕРЖКА ИЗ БАЗЫ ШТАБА
          </div>
          <div style={{ fontSize: 15, lineHeight: 1.65, color: '#F2EFFF', whiteSpace: 'pre-wrap' }}>{d.answer}</div>
          {d.sources.length > 0 && (
            <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 6 }}>
              {d.sources.slice(0, 3).map((s, i) => (
                <a
                  key={i}
                  href={s.url}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: 13, color: '#B79CFF', textDecoration: 'none' }}
                >
                  ↗ {s.title || s.url}
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
      <style>{'@media (min-width: 760px) { .ai-answer-flex { flex-direction: row !important; } }'}</style>
    </motion.div>
  )
}

export default function AiLetopis(): React.JSX.Element {
  const [input, setInput] = useState('')
  const [state, setState] = useState<AnswerState>({ question: '', loading: false, data: null, error: '', image: PRESET_QUESTIONS[0].image })

  const ask = async (question: string, image?: string): Promise<void> => {
    const q = question.trim()
    if (!q || state.loading) return
    setState((s) => ({ ...s, question: q, loading: true, data: null, error: '', image: image ?? s.image }))
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
              void ask(p.question, p.image)
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
