import React, { useEffect, useRef, useState } from 'react'

import { Badge, Button, Div, FormItem, Group, Link, SimpleCell, Spinner, Textarea } from '@vkontakte/vkui'

import { api } from '../api/client'
import { useAuth } from '../auth/authContext'
import type { CallWindow, ChatMode, ChatResponse } from '../types'

type Entry =
  | { kind: 'q'; text: string }
  | { kind: 'a'; data: ChatResponse }
  | { kind: 'e'; text: string }

const MODE_LABELS: Record<ChatMode, string> = {
  struct: 'Структурный',
  local: 'Локальный',
  global: 'Глобальный',
  basic: 'Базовый',
}

// Панель «Рентген»: окна = отдельные вызовы модели (только для admin).
// Каждое окно — полный текст запроса и ответа, ничего не режется.

function CtxWindow({ title, text }: { title: string; text: string | null | undefined }): React.JSX.Element {
  return (
    <Div style={{ padding: 0, marginBottom: 12 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <pre
        style={{
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          fontSize: 12,
          backgroundColor: 'var(--vkui--color_background_secondary)',
          borderRadius: 8,
          padding: 8,
          margin: 0,
          maxHeight: 320,
          overflowY: 'auto',
        }}
      >
        {text || '— пусто —'}
      </pre>
    </Div>
  )
}

export default function ChatPage(): React.JSX.Element {
  const { state } = useAuth()
  const isAdmin = state.role === 'admin'
  const [entries, setEntries] = useState<Entry[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  // Панель «Рентген»: контекст последнего ответа (только admin).
  const [showCtx, setShowCtx] = useState(true)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [entries, sending])

  const send = async (): Promise<void> => {
    const question = input.trim()
    if (!question || sending) {
      return
    }
    setInput('')
    setSending(true)
    setError('')
    setEntries((m) => [...m, { kind: 'q', text: question }])
    try {
      const resp = await api.chat({ question, include_context: isAdmin && showCtx })
      setEntries((m) => [...m, { kind: 'a', data: resp }])
    } catch {
      setEntries((m) => [
        ...m,
        { kind: 'e', text: 'Не удалось получить ответ. Проверьте соединение и попробуйте ещё раз.' },
      ])
    } finally {
      setSending(false)
    }
  }

  const lastAnswer = [...entries].reverse().find((e) => e.kind === 'a')
  const calls: CallWindow[] =
    lastAnswer && lastAnswer.kind === 'a' ? lastAnswer.data.calls ?? [] : []
  const showPanel = isAdmin && showCtx

  return (
    <Group>
      <Div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
        <div style={{ flex: '3 1 480px', minWidth: 0 }}>
      <Div style={{ maxWidth: 640, margin: '0 auto' }}>
        {isAdmin && (
          <Div style={{ padding: 0, marginBottom: 8 }}>
            <Button
              mode="secondary"
              size="s"
              onClick={() => setShowCtx((v) => !v)}
            >
              Рентген: {showCtx ? 'вкл' : 'выкл'}
            </Button>
          </Div>
        )}
        {entries.length === 0 && (
          <Div style={{ textAlign: 'center', color: 'var(--vkui--color_text_secondary)' }}>
            Задайте вопрос о штабе, отрядах и мероприятиях.
          </Div>
        )}

        {entries.map((entry, i) => {
          if (entry.kind === 'q') {
            return (
              <SimpleCell key={i} multiline disabled>
                {entry.text}
              </SimpleCell>
            )
          }
          if (entry.kind === 'e') {
            return <SimpleCell key={i} multiline disabled>{entry.text}</SimpleCell>
          }
          return (
            <Div key={i} style={{ backgroundColor: 'var(--vkui--color_background_secondary)', borderRadius: 12 }}>
              <div style={{ whiteSpace: 'pre-wrap', marginBottom: 8 }}>{entry.data.answer}</div>
              <Div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', padding: 0, marginBottom: 8 }}>
                <Badge mode="prominent" title={entry.data.mode}>
                  {MODE_LABELS[entry.data.mode] ?? entry.data.mode}
                </Badge>
                <Badge title="facts">{entry.data.facts_count} факт(ов)</Badge>
                <Badge title="posts">{entry.data.posts_used} пост(ов)</Badge>
              </Div>
              {entry.data.sources.length > 0 && (
                <Div style={{ padding: 0 }}>
                  {entry.data.sources.map((s, j) => (
                    <Link key={j} href={s.url} target="_blank" rel="noreferrer" style={{ display: 'block', marginBottom: 4 }}>
                      {s.title || s.url}
                    </Link>
                  ))}
                </Div>
              )}
            </Div>
          )
        })}

        {sending && (
          <Div style={{ display: 'flex', gap: 8, alignItems: 'center', color: 'var(--vkui--color_text_secondary)' }}>
            <Spinner size="s" />
            Идёт поиск по графу…
          </Div>
        )}

        {error && (
          <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{error}</Div>
        )}

        <div ref={bottomRef} />
      </Div>

      <Div style={{ maxWidth: 640, margin: '0 auto' }}>
        <FormItem top="Вопрос">
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Например: кто командует отрядом «Погружение»?"
            rows={3}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                void send()
              }
            }}
          />
        </FormItem>
        <Button size="l" stretched onClick={() => void send()} disabled={sending || !input.trim()}>
          Отправить
        </Button>
      </Div>
        </div>
        {showPanel && (
          <div style={{ flex: '2 1 320px', minWidth: 0 }}>
            <Div style={{ maxWidth: 560 }}>
              <div style={{ fontWeight: 600, marginBottom: 8 }}>
                Рентген: вызовы модели
              </div>
              {calls.length === 0 && (
                <div style={{ color: 'var(--vkui--color_text_secondary)' }}>— пусто —</div>
              )}
              {calls.map((c, i) => (
                <CtxWindow key={i} title={c.title} text={c.text} />
              ))}
            </Div>
          </div>
        )}
      </Div>
    </Group>
  )
}