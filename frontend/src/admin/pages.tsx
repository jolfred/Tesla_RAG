import React, { useCallback, useEffect, useState } from 'react'

import { adminApi } from './adminClient'
import type { AdminDocument, AdminProjectDetail } from './adminClient'
import { AdminApiError } from './adminClient'

function errText(e: unknown): string {
  if (e instanceof AdminApiError) {
    try {
      const j = JSON.parse(e.message) as { detail?: string }
      if (j.detail) return j.detail
    } catch {
      // не JSON — показываем как есть
    }
    return e.message || `Ошибка ${e.status}`
  }
  return 'Неизвестная ошибка'
}

function fmtSize(n: number): string {
  if (n > 1048576) return `${(n / 1048576).toFixed(1)} МБ`
  if (n > 1024) return `${(n / 1024).toFixed(0)} КБ`
  return `${n} Б`
}

export function DocsTab(): React.JSX.Element {
  const [docs, setDocs] = useState<AdminDocument[]>([])
  const [projects, setProjects] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const [d, p] = await Promise.all([adminApi.documents(), adminApi.projects()])
      setDocs(d.documents)
      setProjects(p.projects.map((x) => x.slug))
    } catch (e) {
      setErr(errText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const upload = async (): Promise<void> => {
    if (!file) return
    setBusy(true)
    setErr('')
    try {
      await adminApi.uploadDocument(file, title)
      setFile(null)
      setTitle('')
      await reload()
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const attach = async (docId: string, slug: string): Promise<void> => {
    if (!slug) return
    setErr('')
    try {
      await adminApi.attachItem(slug, 'doc', docId)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  const detach = async (docId: string, slug: string): Promise<void> => {
    setErr('')
    try {
      await adminApi.detachItem(slug, 'doc', docId)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div>
      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Загрузить документ</h3>
        <p className="ta-muted" style={{ marginTop: 0 }}>
          PDF, DOCX, TXT, JSON. Название можно задать вручную.
        </p>
        <div className="ta-row">
          <input
            type="file"
            accept=".pdf,.docx,.txt,.json"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <input
            className="ta-input"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Название (необязательно)"
          />
          <button className="ta-btn" onClick={() => void upload()} disabled={busy || !file}>
            Загрузить
          </button>
        </div>
        {err && <p className="ta-error">{err}</p>}
      </div>

      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Загруженные ({docs.length})</h3>
        {loading ? (
          <p className="ta-muted">Загрузка…</p>
        ) : (
          <table className="ta-table">
            <thead>
              <tr>
                <th>Название</th>
                <th>Размер</th>
                <th>Проекты</th>
              </tr>
            </thead>
            <tbody>
              {docs.map((d) => (
                <tr key={d.doc_id}>
                  <td>{d.title}</td>
                  <td>{fmtSize(d.size)}</td>
                  <td>
                    {d.projects.map((s) => (
                      <span key={s} className="ta-pill">
                        {s}{' '}
                        <button
                          onClick={() => void detach(d.doc_id, s)}
                          style={{ border: 0, background: 'none', cursor: 'pointer' }}
                          title="Отвязать"
                        >
                          ×
                        </button>
                      </span>
                    ))}
                    <select
                      className="ta-select"
                      defaultValue=""
                      onChange={(e) => {
                        void attach(d.doc_id, e.target.value)
                        e.target.value = ''
                      }}
                      title="Добавить в проект"
                    >
                      <option value="">+ в проект…</option>
                      {projects
                        .filter((s) => !d.projects.includes(s))
                        .map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

export function ProjectsTab(): React.JSX.Element {
  const [list, setList] = useState<{ slug: string; name: string; description: string }[]>([])
  const [detail, setDetail] = useState<AdminProjectDetail | null>(null)
  const [slug, setSlug] = useState('')
  const [name, setName] = useState('')
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)

  const reload = useCallback(async (keepSlug?: string) => {
    setErr('')
    try {
      const p = await adminApi.projects()
      setList(p.projects)
      const target = keepSlug ?? detail?.slug
      if (target && p.projects.some((x) => x.slug === target)) {
        setDetail(await adminApi.projectDetail(target))
      } else if (!keepSlug) {
        setDetail(null)
      }
    } catch (e) {
      setErr(errText(e))
    }
  }, [detail?.slug])

  useEffect(() => {
    void reload()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const create = async (): Promise<void> => {
    setBusy(true)
    setErr('')
    try {
      const p = await adminApi.createProject({ slug, name, description: '' })
      setSlug('')
      setName('')
      await reload(p.slug)
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (s: string): Promise<void> => {
    if (!window.confirm(`Удалить проект «${s}»? Привязки тоже удалятся, файлы останутся.`)) return
    setErr('')
    try {
      await adminApi.deleteProject(s)
      if (detail?.slug === s) setDetail(null)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div>
      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Новый проект</h3>
        <div className="ta-row">
          <input
            className="ta-input"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            placeholder="slug: shtab, monolit…"
          />
          <input
            className="ta-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название"
          />
          <button className="ta-btn" onClick={() => void create()} disabled={busy || !slug}>
            Создать
          </button>
        </div>
        {err && <p className="ta-error">{err}</p>}
      </div>

      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Проекты ({list.length})</h3>
        <table className="ta-table">
          <tbody>
            {list.map((p) => (
              <tr key={p.slug}>
                <td>
                  <strong>{p.name}</strong> <span className="ta-muted">{p.slug}</span>
                </td>
                <td>
                  <button className="ta-btn secondary" onClick={() => void adminApi.projectDetail(p.slug).then(setDetail).catch((e: unknown) => setErr(errText(e)))}>
                    Состав
                  </button>{' '}
                  <button className="ta-btn danger" onClick={() => void remove(p.slug)}>
                    Удалить
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="ta-card">
          <h3 style={{ margin: '0 0 8px' }}>Состав: {detail.name}</h3>
          {detail.items.length === 0 ? (
            <p className="ta-muted">Пусто. Привяжите документы на вкладке «Документы», группы — на вкладке «VK-группы».</p>
          ) : (
            <table className="ta-table">
              <tbody>
                {detail.items.map((it) => (
                  <tr key={`${it.item_type}:${it.item_id}`}>
                    <td>
                      <span className="ta-pill">{it.item_type}</span> {it.item_id}
                    </td>
                    <td>
                      <button
                        className="ta-btn secondary"
                        onClick={() =>
                          void adminApi
                            .detachItem(detail.slug, it.item_type, it.item_id)
                            .then(() => reload(detail.slug))
                            .catch((e: unknown) => setErr(errText(e)))
                        }
                      >
                        Отвязать
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  )
}
