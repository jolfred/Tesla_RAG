import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AdminApp from './AdminApp'
import { ADMIN_TABS } from './adminTypes'
import { AuthProvider } from '../auth/authContext'
import { AdminSourcesTab } from './operations'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } })
}

describe('AdminApp', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ token: 't', role: 'user', vk_user_id: null, expires_at: '' })))
  })
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('показывает только разделы единой операционной панели', () => {
    expect(ADMIN_TABS.map(x => x.id)).toEqual(['overview', 'materials', 'sources', 'tasks', 'instructions'])
    expect(ADMIN_TABS.map(x => x.title)).not.toContain('Проекты')
  })

  it('гостю показывает экран входа', async () => {
    render(<AuthProvider><AdminApp /></AuthProvider>)
    expect(await screen.findByText(/Вход для редактора/)).toBeTruthy()
  })

  it('принимает прямую ссылку на VK-пост отдельно от группы', async () => {
    const calls: Array<{ url: string; method: string }> = []
    let hasPost = false
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method ?? 'GET'
      calls.push({ url, method })
      if (url.endsWith('/sources') && method === 'GET') {
        const sources = hasPost ? [{ id: 'vkpost:wall-123_456', kind: 'vk_post', domain: '', url: 'https://vk.com/wall-123_456', title: 'Пост', file_path: '', active: true, created_at: '' }] : []
        return jsonResponse({ sources })
      }
      if (url.endsWith('/sources/vk-post') && method === 'POST') {
        hasPost = true
        return jsonResponse({ source: {}, job: {} })
      }
      return jsonResponse({})
    }))

    render(<AdminSourcesTab />)
    fireEvent.change(await screen.findByLabelText('Ссылка на отдельный VK-пост'), { target: { value: 'https://vk.com/wall-123_456' } })
    fireEvent.click(screen.getByRole('button', { name: 'Добавить пост' }))

    expect(await screen.findByText(/Отдельный VK-пост/)).toBeTruthy()
    expect(calls).toContainEqual({ url: '/api/v1/admin/operations/sources/vk-post', method: 'POST' })
    expect(calls.some(call => call.url.endsWith('/jobs/vk-fetch'))).toBe(false)
    expect((screen.getByRole('button', { name: 'Собрать публикации группы' }) as HTMLButtonElement).disabled).toBe(true)
  })
})
