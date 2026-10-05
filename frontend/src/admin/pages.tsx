import React, { useCallback, useEffect, useState } from 'react'

import { adminApi } from './adminClient'
import type { AdminDocument, AdminGroup, AdminJob, AdminProjectDetail } from './adminClient'
import { AdminApiError, STATUS_RU } from './adminClient'

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

const RU2LAT: Record<string, string> = {
  а: 'a', б: 'b', в: 'v', г: 'g', д: 'd', е: 'e', ё: 'yo', ж: 'zh', з: 'z', и: 'i',
  й: 'y', к: 'k', л: 'l', м: 'm', н: 'n', о: 'o', п: 'p', р: 'r', с: 's', т: 't',
  у: 'u', ф: 'f', х: 'h', ц: 'ts', ч: 'ch', ш: 'sh', щ: 'sch', ъ: '', ы: 'y',
  ь: '', э: 'e', ю: 'yu', я: 'ya',
}

// Название -> slug: транслит, малые буквы, дефисы. Пусто -> ''.
export function slugify(name: string): string {
  return name
    .toLowerCase()
    .split('')
    .map((ch) => RU2LAT[ch] ?? ch)
    .join('')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
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
  const [name, setName] = useState('')
  const [slugManual, setSlugManual] = useState('')
  const [slugEdit, setSlugEdit] = useState(false)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const slug = slugManual || slugify(name)

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
      const p = await adminApi.createProject({ slug, name: name.trim() || slug, description: '' })
      setName('')
      setSlugManual('')
      setSlugEdit(false)
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
      setDetail(await adminApi.projectDetail(s))
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div>
      <div className="ta-card">
        <h3 style={{ margin: '0 0 8px' }}>Новый проект</h3>
        <p className="ta-muted" style={{ marginTop: 0 }}>
          Проекты помогают группировать собранные материалы. Ответы чата сейчас строятся по Летописи; отдельная индексация проекта отключена.
        </p>
        <div className="ta-row">
          <input
            className="ta-input"
            style={{ minWidth: 260 }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название: Штаб, Монолит, Лига студентов…"
            title="Человеческое название проекта"
          />
          <button className="ta-btn" onClick={() => void create()} disabled={busy || !slug}>
            Создать
          </button>
        </div>
        <p className="ta-muted" style={{ marginBottom: 0 }}>
          Внутренний ID проекта: <code>{slug || '—'}</code>
          {slugEdit ? (
            <>
              {' '}
              <input
                className="ta-input"
                style={{ width: 180 }}
                value={slugManual}
                onChange={(e) => setSlugManual(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                placeholder="свой id"
              />{' '}
              <button className="ta-btn secondary" onClick={() => { setSlugEdit(false); setSlugManual('') }}>
                Авто
              </button>
            </>
          ) : (
            <>
              {' '}
              <button className="ta-btn secondary" onClick={() => { setSlugManual(slug); setSlugEdit(true) }}>
                Изменить
              </button>
            </>
          )}
        </p>
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

function fmtDate(ts: number): string {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString('ru-RU')
}

function fmtDur(created: string, finished: string): string {
  const t0 = Date.parse(created.replace(' ', 'T') + 'Z')
  if (isNaN(t0)) return '—'
  const t1 = finished ? Date.parse(finished.replace(' ', 'T') + 'Z') : Date.now()
  if (isNaN(t1)) return '—'
  const s = Math.max(0, Math.round((t1 - t0) / 1000))
  if (s < 60) return `${s} c`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} мин ${s % 60} c`
  return `${Math.floor(m / 60)} ч ${m % 60} мин`
}

function paramsSummary(j: AdminJob): string {
  const p = j.params ?? {}
  if (j.kind === 'scrape_posts') {
    const lim = Number(p.limit ?? 0)
    return `${String(p.domain ?? '?')}${lim > 0 ? `, лимит ${lim}` : ', все посты'}`
  }
  if (j.kind === 'scrape_meta') return String(p.domain ?? '?')
  return ''
}

export function QueueTab(): React.JSX.Element {
  const [jobs, setJobs] = useState<AdminJob[]>([])
  const [openLog, setOpenLog] = useState<string | null>(null)
  const [logText, setLogText] = useState('')
  const [editing, setEditing] = useState<AdminJob | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editParams, setEditParams] = useState<Record<string, string>>({})
  const [err, setErr] = useState('')
  const [notice, setNotice] = useState('')

  const reload = useCallback(async () => {
    try {
      setJobs((await adminApi.jobs()).jobs.filter((job) => job.kind !== 'index'))
    } catch (e) {
      setErr(errText(e))
    }
  }, [])

  useEffect(() => {
    void reload()
  }, [reload])

  // Пока что-то выполняется — обновляем список сами каждые 5 секунд.
  const running = jobs.some((j) => j.status === 'running')
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => void reload(), 5000)
    return () => clearInterval(t)
  }, [running, reload])

  const showLog = async (id: string): Promise<void> => {
    try {
      const j = await adminApi.job(id)
      setOpenLog(id)
      setLogText(j.log_tail || '(лог пуст)')
    } catch (e) {
      setErr(errText(e))
    }
  }

  const start = async (id: string): Promise<void> => {
    setErr('')
    setNotice('')
    try {
      await adminApi.startJob(id)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  const remove = async (id: string): Promise<void> => {
    setErr('')
    try {
      await adminApi.deleteJob(id)
      if (editing?.id === id) setEditing(null)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  const prune = async (): Promise<void> => {
    setErr('')
    try {
      const r = await adminApi.pruneJobs()
      setNotice(`Убрано завершённых: ${r.removed}.`)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  const openEdit = (j: AdminJob): void => {
    setEditing(j)
    setEditLabel(j.label)
    const p = j.params ?? {}
    setEditParams({
      limit: String(p.limit ?? 0),
    })
  }

  const saveEdit = async (): Promise<void> => {
    if (!editing) return
    setErr('')
    try {
      const params: Record<string, unknown> = { domain: editing.params?.domain, limit: Math.max(0, parseInt(editParams.limit || '0', 10) || 0) }
      await adminApi.updateJob(editing.id, { label: editLabel, params })
      setEditing(null)
      await reload()
    } catch (e) {
      setErr(errText(e))
    }
  }

  return (
    <div>
      <div className="ta-card">
        <div className="ta-row" style={{ justifyContent: 'space-between' }}>
          <p className="ta-muted" style={{ margin: 0 }}>
            Сюда попадают задачи сбора материалов из вкладки групп. Проверьте что и куда —
            потом «Запустить». Одновременно выполняется одна задача.
          </p>
          <div className="ta-row">
            <button className="ta-btn secondary" onClick={() => void reload()}>
              Обновить
            </button>
            <button
              className="ta-btn secondary"
              onClick={() => void prune()}
              title="Удалить из списка все готовые и упавшие задачи (файлы и графы не трогает)"
            >
              Убрать готовые
            </button>
          </div>
        </div>
        {err && <p className="ta-error">{err}</p>}
        {notice && <p style={{ color: '#067647', fontSize: 14 }}>{notice}</p>}
      </div>

      <div className="ta-card">
        {jobs.length === 0 ? (
          <p className="ta-muted">Очередь пуста.</p>
        ) : (
          <table className="ta-table">
            <thead>
              <tr>
                <th>Задача</th>
                <th>Статус</th>
                <th>Длительность</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id} style={j.status === 'running' ? { background: '#f0fdf4' } : undefined}>
                  <td>
                    <strong>{j.label || j.kind}</strong>
                    <br />
                    <span className="ta-muted">{paramsSummary(j)}</span>
                    {j.project_slug && <span className="ta-pill">{j.project_slug}</span>}
                  </td>
                  <td>
                    {STATUS_RU[j.status] ?? j.status}
                    {j.error && (
                      <div className="ta-error" style={{ fontSize: 13 }}>
                        {j.error}
                      </div>
                    )}
                  </td>
                  <td className="ta-muted" style={{ whiteSpace: 'nowrap' }}>
                    {fmtDur(j.created_at, j.finished_at)}
                  </td>
                  <td>
                    <div className="ta-row">
                      {j.status !== 'running' && (
                        <button
                          className="ta-btn"
                          onClick={() => void start(j.id)}
                          disabled={running}
                          title={running ? 'Дождитесь конца выполняющейся задачи' : 'Запустить сейчас'}
                        >
                          Запустить
                        </button>
                      )}
                      {j.status === 'queued' && (
                        <button className="ta-btn secondary" onClick={() => openEdit(j)} title="Поменять название и параметры до запуска">
                          Изменить
                        </button>
                      )}
                      {j.status !== 'running' && (
                        <button className="ta-btn secondary" onClick={() => void remove(j.id)} title="Убрать из очереди (файлы и графы не трогает)">
                          Удалить
                        </button>
                      )}
                      <button className="ta-btn secondary" onClick={() => void showLog(j.id)}>
                        Лог
                      </button>
                    </div>
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

      {editing && (
        <div className="ta-card">
          <h3 style={{ margin: '0 0 8px' }}>Изменить: {editing.label || editing.kind}</h3>
          <div className="ta-row" style={{ marginBottom: 8 }}>
            <input
              className="ta-input"
              style={{ minWidth: 260 }}
              value={editLabel}
              onChange={(e) => setEditLabel(e.target.value)}
              placeholder="Название задачи"
              title="Название видно только в этом списке"
            />
          </div>
          <div className="ta-row">
              <input
                className="ta-input"
                style={{ width: 170 }}
                type="number"
                min={0}
                value={editParams.limit}
                onChange={(e) => setEditParams((v) => ({ ...v, limit: e.target.value }))}
                title="Сколько свежих постов скачать. 0 = все доступные."
              />
              <span className="ta-muted">лимит постов (0 = все)</span>
          </div>
          <div className="ta-row" style={{ marginTop: 8 }}>
            <button className="ta-btn" onClick={() => void saveEdit()}>
              Сохранить
            </button>
            <button className="ta-btn secondary" onClick={() => setEditing(null)}>
              Отмена
            </button>
          </div>
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
  const [limit, setLimit] = useState('0')
  const [notice, setNotice] = useState('')

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

  const queue = async (domain: string, task: 'posts' | 'meta'): Promise<void> => {
    setErr('')
    setNotice('')
    try {
      const lim = Math.max(0, parseInt(limit || '0', 10) || 0)
      await adminApi.queueScrape(domain, task, task === 'posts' ? lim : 0)
      setNotice(`«${domain}» добавлено в очередь — запуск на вкладке «Очередь».`)
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
        <p className="ta-muted" style={{ marginTop: 0 }}>
          Лимит постов для кнопок «Посты»:{' '}
          <input
            className="ta-input"
            style={{ width: 90 }}
            type="number"
            min={0}
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
            title="Сколько свежих постов скачать с группы. 0 = все доступные."
          />{' '}
          (0 = все)
        </p>
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
                      <button
                        className="ta-btn secondary"
                        onClick={() => void queue(g.domain, 'posts')}
                        title="Собрать посты группы для последующей проверки и компиляции в Летопись"
                      >
                        Посты в очередь
                      </button>
                      <button
                        className="ta-btn secondary"
                        onClick={() => void queue(g.domain, 'meta')}
                        title="Мета = название, описание и контакты группы (без постов). Нужно для карточек отрядов."
                      >
                        Мета в очередь
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {notice && <p style={{ color: '#067647', fontSize: 14 }}>{notice}</p>}
      </div>
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
  const [question, setQuestion] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [res, setRes] = useState<ChatResult | null>(null)

  const ask = async (): Promise<void> => {
    if (!question.trim()) return
    setBusy(true)
    setErr('')
    setRes(null)
    try {
      setRes(await adminApi.adminChat(question.trim(), ''))
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
        <p className="ta-muted" style={{ marginBottom: 0 }}>Ответ проверяется по Летописи целиком. Проекты пока не подключены как отдельные источники.</p>
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
