import React, { useEffect, useRef, useState } from 'react'

import { Badge, Button, Div, FormItem, Group, Link, SimpleCell, Spinner, Textarea } from '@vkontakte/vkui'

import { api } from '../api/client'
import type { ChatMode, ChatResponse } from '../types'

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

export default function ChatPage(): React.JSX.Element {
  const [entries, setEntries] = useState<Entry[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
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
      const resp = await api.chat({ question })
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

  return (
    <Group>
      <Div style={{ maxWidth: 640, margin: '0 auto' }}>
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
    </Group>
  )
}