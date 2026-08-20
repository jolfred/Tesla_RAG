import React, { useEffect, useState } from 'react'

import { Button, Card, Div, Group, Header, Input, SimpleCell, Spinner } from '@vkontakte/vkui'

import { api } from '../api/client'
import { useAuth } from '../auth/authContext'
import type { StatusResponse } from '../types'

function formatExpiry(iso: string | null): string {
  if (!iso) {
    return '—'
  }
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('ru-RU')
}

export default function StatusPage(): React.JSX.Element {
  const { state, loginAdmin, logout } = useAuth()
  const [status, setStatus] = useState<StatusResponse | null>(null)
  const [statusError, setStatusError] = useState('')
  const [showAdmin, setShowAdmin] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [adminBusy, setAdminBusy] = useState(false)
  const [adminError, setAdminError] = useState('')

  useEffect(() => {
    api
      .status()
      .then(setStatus)
      .catch(() => setStatusError('Не удалось загрузить статус сервиса'))
  }, [])

  const doLoginAdmin = async (): Promise<void> => {
    setAdminBusy(true)
    setAdminError('')
    try {
      await loginAdmin(apiKey)
      setShowAdmin(false)
      setApiKey('')
    } catch {
      setAdminError('Неверный ключ администратора')
    } finally {
      setAdminBusy(false)
    }
  }

  const doLogout = async (): Promise<void> => {
    await logout()
  }

  return (
    <Group>
      <Header>Текущая сессия</Header>
      <SimpleCell multiline>
        Роль: {state.status === 'loading' ? '…' : state.role === 'admin' ? 'Администратор' : 'Гость'}
      </SimpleCell>
      <SimpleCell multiline>VK: {state.isVK ? 'да' : 'нет'}</SimpleCell>
      <SimpleCell multiline>Токен действует до: {formatExpiry(state.expiresAt)}</SimpleCell>

      {showAdmin ? (
        <Div>
          <Input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="ADMIN_API_KEY"
          />
          {adminError && (
            <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{adminError}</Div>
          )}
          <Div style={{ display: 'flex', gap: 8 }}>
            <Button size="m" onClick={() => void doLoginAdmin()} disabled={adminBusy || !apiKey}>
              {adminBusy ? <Spinner size="s" /> : 'Войти'}
            </Button>
            <Button size="m" mode="tertiary" onClick={() => setShowAdmin(false)}>
              Отмена
            </Button>
          </Div>
        </Div>
      ) : state.role === 'admin' ? (
        <Div>
          <Button size="m" mode="secondary" appearance="negative" onClick={() => void doLogout()}>
            Выйти
          </Button>
        </Div>
      ) : (
        <Div>
          <Button size="m" onClick={() => setShowAdmin(true)}>
            Войти как админ
          </Button>
        </Div>
      )}

      <Header>Статус сервиса</Header>
      {!status && !statusError && (
        <Div>
          <Spinner size="m" />
        </Div>
      )}
      {statusError && <Div style={{ color: 'var(--vkui--color_text_negative)' }}>{statusError}</Div>}
      {status && (
        <Card mode="outline" style={{ margin: '0 12px 12px' }}>
          <Div>
            <SimpleCell multiline>Статус: {status.status}</SimpleCell>
            <SimpleCell multiline>Документы: {status.documents_count}</SimpleCell>
            <SimpleCell multiline>Векторные точки (локальный Qdrant): {status.qdrant_points}</SimpleCell>
            <SimpleCell multiline>Neo4j: {status.neo4j_nodes} узлов, {status.neo4j_relations} связей</SimpleCell>
            <SimpleCell multiline>Ollama: {status.ollama_available ? 'доступна' : 'недоступна'}</SimpleCell>
            {status.errors.length > 0 && (
              <Div style={{ color: 'var(--vkui--color_text_negative)' }}>
                Ошибки: {status.errors.join('; ')}
              </Div>
            )}
          </Div>
        </Card>
      )}
      <Div style={{ color: 'var(--vkui--color_text_secondary)', fontSize: 13 }}>
        Сведения информационные: экран показывает локальный Qdrant; точные счётчики RAG — в M3.
      </Div>
    </Group>
  )
}