import React, { useEffect, useState } from 'react'

import { useAuth } from '../auth/authContext'
import { adminApi } from './adminClient'
import './admin.css'
import { ADMIN_TABS } from './adminTypes'
import type { AdminTab } from './adminTypes'
import { tabContent } from './tabs'

function tabFromUrl(): AdminTab {
  const seg = window.location.pathname.split('/')[2]
  return ADMIN_TABS.some((t) => t.id === seg) ? (seg as AdminTab) : 'docs'
}

function AdminLogin(): React.JSX.Element {
  const { loginAdmin } = useAuth()
  const [key, setKey] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  const submit = async (): Promise<void> => {
    setBusy(true)
    setErr('')
    try {
      await loginAdmin(key)
      setKey('')
    } catch {
      setErr('Неверный ключ администратора')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="tesla-admin">
      <div className="ta-main" style={{ margin: '60px auto' }}>
        <div className="ta-card">
          <h1 className="ta-title">Вход в админку</h1>
          <p className="ta-muted">Нужен ADMIN_API_KEY. Это отдельный сайтик, не VK.</p>
          <div className="ta-row" style={{ marginTop: 12 }}>
            <input
              className="ta-input"
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="ADMIN_API_KEY"
              onKeyDown={(e) => {
                if (e.key === 'Enter') void submit()
              }}
            />
            <button className="ta-btn" onClick={() => void submit()} disabled={busy || !key}>
              Войти
            </button>
          </div>
          {err && <p className="ta-error">{err}</p>}
        </div>
      </div>
    </div>
  )
}

export default function AdminApp(): React.JSX.Element {
  const { state, logout } = useAuth()
  const [tab, setTab] = useState<AdminTab>(() => tabFromUrl())
  const [apiOk, setApiOk] = useState<string>('…')

  useEffect(() => {
    document.body.classList.remove('tesla-landing')
    return () => undefined
  }, [])

  useEffect(() => {
    window.history.replaceState(null, '', `/admin/${tab}`)
  }, [tab])

  useEffect(() => {
    if (state.role === 'admin') {
      adminApi
        .status()
        .then((s) => setApiOk(`API ok · проектов: ${s.projects_count} · активных задач: ${s.jobs_active}`))
        .catch(() => setApiOk('API недоступен'))
    }
  }, [state.role])

  if (state.status === 'loading') {
    return (
      <div className="tesla-admin">
        <div className="ta-main">
          <p className="ta-muted">Загрузка…</p>
        </div>
      </div>
    )
  }

  if (state.role !== 'admin') {
    return <AdminLogin />
  }

  const active = ADMIN_TABS.find((t) => t.id === tab) ?? ADMIN_TABS[0]

  return (
    <div className="tesla-admin">
      <div className="ta-shell">
        <aside className="ta-side">
          <div className="ta-logo">
            Тесла · Админка<small>{apiOk}</small>
          </div>
          <nav className="ta-nav">
            {ADMIN_TABS.map((t) => (
              <button
                key={t.id}
                className={t.id === tab ? 'active' : ''}
                onClick={() => setTab(t.id)}
              >
                {t.title}
              </button>
            ))}
          </nav>
          <nav className="ta-nav" style={{ marginTop: 16 }}>
            <button onClick={() => void logout()}>Выйти</button>
          </nav>
        </aside>
        <main className="ta-main">
          <h1 className="ta-title">{active.title}</h1>
          <p className="ta-muted" style={{ marginTop: 0 }}>
            {active.hint}
          </p>
          {tabContent(tab)}
        </main>
      </div>
    </div>
  )
}
