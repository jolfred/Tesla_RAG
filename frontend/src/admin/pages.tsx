import React, { useCallback, useEffect, useState } from 'react'

import { adminApi } from './adminClient'
import type { AdminDocument, AdminGroup, AdminJob, AdminProjectDetail } from './adminClient'
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
  const [stats, setStats] = useState<Record<string, { n: number; r: number; q: number; err: string }>>({})
  const [idxModel, setIdxModel] = useState('gigachat')
  const [idxExtractor, setIdxExtractor] = useState('transformer')
  const [idxMinDate, setIdxMinDate] = useState('')
  const [idxForce, setIdxForce] = useState(false)
  const [jobsTick, setJobsTick] = useState(0)
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

  const openDetail = async (s: string): Promise<void> => {
    setErr('')
    try {
      const [d, st] = await Promise.all([adminApi.projectDetail(s), adminApi.projectStats(s)])
      setDetail(d)
      setStats((prev) => ({
        ...prev,
        [s]: { n: st.neo4j_nodes, r: st.neo4j_relations, q: st.qdrant_points, err: st.error },
      }))
    } catch (e) {
      setErr(errText(e))
    }
  }

  const index = async (): Promise<void> => {
    if (!detail) return
    setErr('')
    try {
      await adminApi.indexProject(detail.slug, {
        model: idxModel,
        extractor: idxExtractor,
        min_date: idxMinDate,
        force: idxForce,
      })
      setJobsTick((n) => n + 1)
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
                  <button className="ta-btn secondary" onClick={() => void openDetail(p.slug)}>
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
          {stats[detail.slug] && (
            <p className="ta-muted" style={{ marginTop: 0 }}>
              Граф: {stats[detail.slug].n} узлов, {stats[detail.slug].r} связей · Qdrant:{' '}
              {stats[detail.slug].q} точек
              {stats[detail.slug].err ? ` · ⚠ ${stats[detail.slug].err}` : ''}
            </p>
          )}
          <div className="ta-row" style={{ marginBottom: 12 }}>
            <select className="ta-select" value={idxModel} onChange={(e) => setIdxModel(e.target.value)}>
              <option value="gigachat">gigachat</option>
              <option value="gemma">gemma</option>
              <option value="proxyapi">proxyapi</option>
            </select>
            <select
              className="ta-select"
              value={idxExtractor}
              onChange={(e) => setIdxExtractor(e.target.value)}
            >
              <option value="transformer">transformer (v2)</option>
              <option value="legacy">legacy</option>
            </select>
            <input
              className="ta-input"
              value={idxMinDate}
              onChange={(e) => setIdxMinDate(e.target.value)}
              placeholder="min-date (пусто = все)"
              style={{ width: 170 }}
            />
            <label style={{ fontSize: 14 }}>
              <input type="checkbox" checked={idxForce} onChange={(e) => setIdxForce(e.target.checked)} />{' '}
              force
            </label>
            <button className="ta-btn" onClick={() => void index()}>
              Индексировать проект
            </button>
          </div>
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

      <JobsBlock refreshKey={jobsTick} />
    </div>
  )
}

function fmtDate(ts: number): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('ru-RU')
}

export function JobsBlock({ refreshKey }: { refreshKey: number }): React.JSX.Element {
  const [jobs, setJobs] = useState<AdminJob[]>([])
  const [openLog, setOpenLog] = useState<string | null>(null)
  const [logText, setLogText] = useState('')
  const [err, setErr] = useState('')

  const reload = useCallback(async () => {
    try {
      setJobs((await adminApi.jobs()).jobs)
    } catch (e) {
      setErr(errText(e))
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload, refreshKey])

  const showLog = async (id: string): Promise<void> => {
    try {
      const j = await adminApi.job(id)
      setOpenLog(id)
      setLogText(j.log_tail || '(лог пуст)')
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div className="ta-card">
      <div className="ta-row" style={{ justifyContent: 'space-between' }}>
        <h3 style={{ margin: 0 }}>Задачи</h3>
        <button className="ta-btn secondary" onClick={() => void reload()}>
          Обновить
        </button>
      </div>
      {err && <p className="ta-error">{err}</p>}
      {jobs.length === 0 ? (
        <p className="ta-muted">Задач пока нет.</p>
      ) : (
        <table className="ta-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Тип</th>
              <th>Проект</th>
              <th>Статус</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.id}>
                <td>
                  <code>{j.id}</code>
                </td>
                <td>{j.kind}</td>
                <td>{j.project_slug || '—'}</td>
                <td>
                  {j.status}
                  {j.error ? ` (${j.error})` : ''}
                </td>
                <td>
                  <button className="ta-btn secondary" onClick={() => void showLog(j.id)}>
                    Лог
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {openLog && (
        <div>
          <h4 style={{ marginBottom: 4 }}>Лог {openLog}</h4>
          <pre className="ta-log">{logText}</pre>
        </div>
      )}
    </div>
  )
}

export function GroupsTab(): React.JSX.Element {
  const [groups, setGroups] = useState<AdminGroup[]>([])
  const [projects, setProjects] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [err, setErr] = useState('')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  const [jobsTick, setJobsTick] = useState(0)

  const reload = useCallback(async () => {
    setLoading(true)
    setErr('')
    try {
      const [g, p] = await Promise.all([adminApi.groups(), adminApi.projects()])
      setGroups(g.groups)
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

  const add = async (): Promise<void> => {
    setBusy(true)
    setErr('')
    try {
      await adminApi.addGroup(url)
      setUrl('')
      await reload()
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const scrape = async (domain: string, meta_only: boolean): Promise<void> => {
    setErr('')
    try {
      await adminApi.scrapeGroup(domain, meta_only)
      setJobsTick((n) => n + 1)
    } catch (e) {
      setErr(errText(e))
    }
  }

  const attach = async (domain: string, slug: string): Promise<void> => {
    if (!slug) return
    setErr('')
    try {
      await adminApi.attachItem(slug, 'vk_group', domain)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div>
      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Добавить группу</h3>
        <div className="ta-row">
          <input
            className="ta-input"
            style={{ minWidth: 280 }}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://vk.ru/…"
          />
          <button className="ta-btn" onClick={() => void add()} disabled={busy || !url}>
            Добавить
          </button>
        </div>
        {err && <p className="ta-error">{err}</p>}
      </div>

      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Группы ({groups.length})</h3>
        {loading ? (
          <p className="ta-muted">Загрузка…</p>
        ) : (
          <table className="ta-table">
            <thead>
              <tr>
                <th>Группа</th>
                <th>Постов</th>
                <th>Мета</th>
                <th>Проекты</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {groups.map((g) => (
                <tr key={g.domain} style={g.enabled ? undefined : { opacity: 0.55 }}>
                  <td>
                    <a href={g.url} target="_blank" rel="noreferrer">
                      {g.domain}
                    </a>
                    {!g.enabled && <span className="ta-muted"> (выкл. в txt)</span>}
                  </td>
                  <td>
                    {g.posts_count > 0 ? `${g.posts_count} · ${fmtDate(g.posts_mtime)}` : '—'}
                  </td>
                  <td>{g.meta_name || '—'}</td>
                  <td>
                    {g.projects.map((s) => (
                      <span key={s} className="ta-pill">
                        {s}
                      </span>
                    ))}
                    <select
                      className="ta-select"
                      defaultValue=""
                      onChange={(e) => {
                        void attach(g.domain, e.target.value)
                        e.target.value = ''
                      }}
                      title="Добавить в проект"
                    >
                      <option value="">+ в проект…</option>
                      {projects
                        .filter((s) => !g.projects.includes(s))
                        .map((s) => (
                          <option key={s} value={s}>
                            {s}
                          </option>
                        ))}
                    </select>
                  </td>
                  <td>
                    <div className="ta-row">
                      <button className="ta-btn secondary" onClick={() => void scrape(g.domain, false)}>
                        Спарсить
                      </button>
                      <button className="ta-btn secondary" onClick={() => void scrape(g.domain, true)}>
                        Мета
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <JobsBlock refreshKey={jobsTick} />
    </div>
  )
}

interface ChatResult {
  answer: string
  sources: { title: string; url: string }[]
  mode: string
  facts_count: number
  posts_used: number
  calls: { title: string; text: string }[] | null
  trace_id: string | null
}

export function ChatTab(): React.JSX.Element {
  const [projects, setProjects] = useState<string[]>([])
  const [slug, setSlug] = useState('')
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<ChatResult | null>(null)

  useEffect(() => {
    adminApi
      .projects()
      .then((p) => setProjects(p.projects.map((x) => x.slug)))
      .catch((e: unknown) => setErr(errText(e)))
  }, [])

  const ask = async (): Promise<void> => {
    if (!question.trim()) return
    setBusy(true)
    setErr('')
    setRes(null)
    try {
      setRes(await adminApi.adminChat(question.trim(), slug))
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div className="ta-card">
        <div className="ta-row">
          <select className="ta-select" value={slug} onChange={(e) => setSlug(e.target.value)}>
            <option value="">Общий граф (без проекта)</option>
            {projects.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <input
            className="ta-input"
            style={{ flex: 1, minWidth: 240 }}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Вопрос для проверки…"
            onKeyDown={(e) => {
              if (e.key === 'Enter') void ask()
            }}
          />
          <button className="ta-btn" onClick={() => void ask()} disabled={busy || !question.trim()}>
            Спросить
          </button>
        </div>
        {err && <p className="ta-error">{err}</p>}
      </div>

      {busy && (
        <div className="ta-card">
          <p className="ta-muted">Думаю… (идёт через GigaChat, до ~2 минут)</p>
        </div>
      )}

      {res && (
        <div>
          <div className="ta-card">
            <p className="ta-muted" style={{ marginTop: 0 }}>
              mode: {res.mode} · фактов: {res.facts_count} · постов: {res.posts_used}
              {res.trace_id ? ` · trace: ${res.trace_id}` : ''}
            </p>
            <p style={{ whiteSpace: 'pre-wrap' }}>{res.answer}</p>
            {res.sources.length > 0 && (
              <ul>
                {res.sources.map((s, i) => (
                  <li key={i}>
                    <a href={s.url} target="_blank" rel="noreferrer">
                      {s.title}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {res.calls?.map((c, i) => (
            <details key={i} className="ta-card">
              <summary style={{ cursor: 'pointer', fontWeight: 600 }}>{c.title}</summary>
              <pre className="ta-log">{c.text}</pre>
            </details>
          ))}
        </div>
      )}
    </div>
  )
}

interface AdminPrompt {
  key: string
  title: string
  text: string
  custom: boolean
  updated_at: string
}

export function PromptsTab(): React.JSX.Element {
  const [prompts, setPrompts] = useState<AdminPrompt[]>([])
  const [sel, setSel] = useState('')
  const [text, setText] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState('')

  const reload = useCallback(async (keep?: string) => {
    setLoading(true)
    setErr('')
    try {
      const p = await adminApi.prompts()
      setPrompts(p.prompts)
      const target = keep ?? sel
      const found = p.prompts.find((x) => x.key === target) ?? p.prompts[0]
      if (found) {
        setSel(found.key)
        setText(found.text)
      }
    } catch (e) {
      setErr(errText(e))
    } finally {
      setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const pick = (key: string): void => {
    setSel(key)
    setSaved('')
    const found = prompts.find((x) => x.key === key)
    if (found) setText(found.text)
  }

  const save = async (): Promise<void> => {
    setBusy(true)
    setErr('')
    setSaved('')
    try {
      await adminApi.setPrompt(sel, text)
      setSaved('Сохранено — применится к следующим запросам и задачам без рестарта.')
      await reload(sel)
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const reset = async (): Promise<void> => {
    setBusy(true)
    setErr('')
    setSaved('')
    try {
      const r = await adminApi.resetPrompt(sel)
      setText(r.text)
      setSaved('Сброшено к дефолту из кода.')
      await reload(sel)
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const active = prompts.find((x) => x.key === sel)

  return (
    <div>
      <div className="ta-card">
        <p className="ta-muted" style={{ marginTop: 0 }}>
          Промпты всех уровней генерации. «Изменён» = override из БД, иначе дефолт из кода.
          {loading ? '' : ''}
        </p>
        {loading ? (
          <p className="ta-muted">Загрузка…</p>
        ) : (
          <div className="ta-row">
            {prompts.map((p) => (
              <button
                key={p.key}
                className={p.key === sel ? 'ta-btn' : 'ta-btn secondary'}
                onClick={() => pick(p.key)}
              >
                {p.title}
                {p.custom ? ' ●' : ''}
              </button>
            ))}
          </div>
        )}
      </div>

      {active && (
        <div className="ta-card">
          <h3 style={{ margin: '0 0 8px' }}>
            {active.title} {active.custom ? <span className="ta-pill">изменён</span> : <span className="ta-pill">дефолт</span>}
          </h3>
          <textarea
            className="ta-textarea"
            style={{ minHeight: 320 }}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
          <div className="ta-row" style={{ marginTop: 8 }}>
            <button className="ta-btn" onClick={() => void save()} disabled={busy}>
              Сохранить
            </button>
            <button className="ta-btn secondary" onClick={() => void reset()} disabled={busy}>
              Сбросить к дефолту
            </button>
          </div>
          {err && <p className="ta-error">{err}</p>}
          {saved && <p style={{ color: '#067647', fontSize: 14 }}>{saved}</p>}
        </div>
      )}
    </div>
  )
}

interface GraphData {
  source_model: string
  browser_url: string
  nodes: { id: string; label: string; name: string }[]
  edges: { a: string; rel: string; b: string }[]
}

const LABEL_COLORS: Record<string, string> = {
  Person: '#2563eb',
  Squad: '#16a34a',
  Organization: '#16a34a',
  Entity: '#6b7280',
  Event: '#dc2626',
  Project: '#9333ea',
  Role: '#ea580c',
  Award: '#ca8a04',
  Location: '#0891b2',
  Profession: '#4d7c0f',
}

export function GraphsTab(): React.JSX.Element {
  const [projects, setProjects] = useState<string[]>([])
  const [slug, setSlug] = useState(
    () => new URLSearchParams(window.location.search).get('project') ?? '',
  )
  const [data, setData] = useState<GraphData | null>(null)
  const [loading, setLoading] = useState(false)
  const [err, setErr] = useState('')

  useEffect(() => {
    adminApi
      .projects()
      .then((p) => setProjects(p.projects.map((x) => x.slug)))
      .catch((e: unknown) => setErr(errText(e)))
  }, [])

  const load = useCallback(async (s: string) => {
    setLoading(true)
    setErr('')
    setData(null)
    try {
      setData(await adminApi.graphExport(s))
    } catch (e) {
      setErr(errText(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    const url = new URL(window.location.href)
    if (slug) {
      url.searchParams.set('project', slug)
    } else {
      url.searchParams.delete('project')
    }
    window.history.replaceState(null, '', `/admin/graphs${url.search}`)
    if (slug) void load(slug)
    else setData(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug])

  const permalink = `${window.location.origin}/admin/graphs${slug ? `?project=${encodeURIComponent(slug)}` : ''}`
  const nodes = data?.nodes ?? []
  const R = 220
  const pos = new Map<string, { x: number; y: number }>()
  nodes.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(nodes.length, 1)
    pos.set(n.id, { x: 260 + R * Math.cos(a), y: 260 + R * Math.sin(a) })
  })
  const ids = new Set(nodes.map((n) => n.id))
  const drawn = (data?.edges ?? []).filter((e) => ids.has(e.a) && ids.has(e.b)).slice(0, 300)

  return (
    <div>
      <div className="ta-card">
        <div className="ta-row">
          <select className="ta-select" value={slug} onChange={(e) => setSlug(e.target.value)}>
            <option value="">Общий граф (llmgraph_gigachat)</option>
            {projects.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {slug && (
            <button className="ta-btn secondary" onClick={() => void load(slug)} disabled={loading}>
              Обновить
            </button>
          )}
        </div>
        {err && <p className="ta-error">{err}</p>}
        <p className="ta-muted" style={{ marginBottom: 0 }}>
          Отдельная ссылка на граф:{' '}
          <a href={permalink} target="_blank" rel="noreferrer">
            {permalink}
          </a>
          {data && (
            <>
              {' · '}
              <a href={data.browser_url} target="_blank" rel="noreferrer">
                Открыть в Neo4j Browser
              </a>
            </>
          )}
        </p>
      </div>

      {loading && (
        <div className="ta-card">
          <p className="ta-muted">Загрузка графа…</p>
        </div>
      )}

      {data && (
        <div className="ta-card">
          <h3 style={{ margin: '0 0 8px' }}>
            {data.source_model}: {nodes.length} узлов, {drawn.length} связей (показаны первые)
          </h3>
          {nodes.length > 0 ? (
            <svg viewBox="0 0 520 520" style={{ width: '100%', maxWidth: 640 }}>
              {drawn.map((e, i) => {
                const p1 = pos.get(e.a)
                const p2 = pos.get(e.b)
                if (!p1 || !p2) return null
                return <line key={i} x1={p1.x} y1={p1.y} x2={p2.x} y2={p2.y} stroke="#d1d5db" strokeWidth={1} />
              })}
              {nodes.map((n) => {
                const p = pos.get(n.id)
                if (!p) return null
                return (
                  <g key={n.id}>
                    <circle cx={p.x} cy={p.y} r={9} fill={LABEL_COLORS[n.label] ?? '#6b7280'}>
                      <title>
                        {n.name} [{n.label}]
                      </title>
                    </circle>
                    <text x={p.x + 12} y={p.y + 4} fontSize={10} fill="#374151">
                      {(n.name || n.id).slice(0, 24)}
                    </text>
                  </g>
                )
              })}
            </svg>
          ) : (
            <p className="ta-muted">В ветке пока пусто — запустите индексацию проекта.</p>
          )}
        </div>
      )}
    </div>
  )
}

interface AdminSetting {
  key: string
  title: string
  in_db: boolean
  in_env: boolean
}

export function KeysTab(): React.JSX.Element {
  const [settings, setSettings] = useState<AdminSetting[]>([])
  const [values, setValues] = useState<Record<string, string>>({})
  const [checks, setChecks] = useState<Record<string, { ok: boolean; info: string }>>({})
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [saved, setSaved] = useState('')

  const reload = useCallback(async () => {
    setErr('')
    try {
      setSettings((await adminApi.settings()).settings)
    } catch (e) {
      setErr(errText(e))
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  const save = async (key: string): Promise<void> => {
    setBusy(key)
    setErr('')
    setSaved('')
    try {
      await adminApi.setSetting(key, values[key] ?? '')
      setValues((v) => ({ ...v, [key]: '' }))
      setSaved(`${key}: сохранено, применяется без рестарта.`)
      await reload()
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy('')
    }
  }

  const check = async (key: string): Promise<void> => {
    setBusy(key)
    setErr('')
    try {
      const r = await adminApi.checkSetting(key)
      setChecks((c) => ({ ...c, [key]: r }))
    } catch (e) {
      setErr(errText(e))
    } finally {
      setBusy('')
    }
  }

  return (
    <div>
      <div className="ta-card">
        <p className="ta-muted" style={{ marginTop: 0 }}>
          Значения хранятся в admin.db и перекрывают .env без рестарта: клиенты читают их при
          каждом обращении, фоновые задачи получают через env. Значения никогда не показываются —
          только факт наличия. Пустое поле + «Сохранить» = откат к .env.
        </p>
        {err && <p className="ta-error">{err}</p>}
        {saved && <p style={{ color: '#067647', fontSize: 14 }}>{saved}</p>}
        <table className="ta-table">
          <thead>
            <tr>
              <th>Ключ</th>
              <th>Статус</th>
              <th>Новое значение</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {settings.map((s) => (
              <tr key={s.key}>
                <td>
                  <code>{s.key}</code>
                  <br />
                  <span className="ta-muted">{s.title}</span>
                </td>
                <td>
                  {s.in_db ? <span className="ta-pill">в БД ●</span> : null}
                  {s.in_env ? <span className="ta-pill">в env</span> : null}
                  {!s.in_db && !s.in_env ? <span className="ta-pill">не задан</span> : null}
                  {checks[s.key] && (
                    <div style={{ fontSize: 13, marginTop: 4 }}>
                      {checks[s.key].ok ? '✅ ' : '❌ '}
                      {checks[s.key].info}
                    </div>
                  )}
                </td>
                <td>
                  <input
                    className="ta-input"
                    type="password"
                    value={values[s.key] ?? ''}
                    onChange={(e) => setValues((v) => ({ ...v, [s.key]: e.target.value }))}
                    placeholder="****"
                    style={{ width: 220 }}
                  />
                </td>
                <td>
                  <div className="ta-row">
                    <button className="ta-btn secondary" onClick={() => void save(s.key)} disabled={busy === s.key}>
                      Сохранить
                    </button>
                    <button className="ta-btn secondary" onClick={() => void check(s.key)} disabled={busy === s.key}>
                      Проверить
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
