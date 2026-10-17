import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import EditorialApp from './EditorialApp';
import { AuthProvider } from '../auth/authContext';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

describe('EditorialApp', () => {
  let fetchMock: ReturnType<typeof vi.fn>;
  let draftConflict = false;
  let articleReads = 0;
  beforeEach(() => {
    draftConflict = false;
    articleReads = 0;
    localStorage.setItem('tesla_graphrag_token', 'admin-test');
    fetchMock = vi.fn(async (input: RequestInfo | URL, _init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith('/api/v1/auth/me')) return response({ role: 'admin', vk_user_id: null, expires_at: '' });
      if (url.includes('/api/v1/editorial/articles')) return response({ articles: [{ slug: 'hq/index', title: 'Штаб СО КГЭУ «Тесла»', kind: 'hq', revision: 'abc123456789', status: 'published', has_draft: false, updated_at: '' }] });
      if (url.includes('/api/v1/editorial/article?')) { articleReads += 1; return response({ slug: 'hq/index', title: 'Штаб СО КГЭУ «Тесла»', markdown: '# Статья\n\n| Роль | Статья |\n| --- | --- |\n| Командир | [[people/example|Алексей]] |', revision: 'abc123456789', sources: [{ url: 'https://vk.com/example', title: 'Публикация', group_name: 'Штаб', published_at: '2026-01-02' }], draft: null }); }
      if (url.endsWith('/api/v1/editorial/draft')) return draftConflict ? response({ detail: 'stale revision' }, 409) : response({ ok: true, draft: { markdown: '# Черновик\n\nИзменение.', base_revision: 'abc123456789', revision: 'draft123456', updated_at: '' } });
      if (url.endsWith('/api/v1/editorial/publish')) return response({ ok: true, slug: 'hq/index', revision: 'published123' });
      if (url.includes('/api/v1/editorial/discussions')) return response({ discussions: [] });
      return response({});
    });
    vi.stubGlobal('fetch', fetchMock);
  });
  afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

  it('separates draft saving from explicit publishing with a reason', async () => {
    render(<AuthProvider><EditorialApp /></AuthProvider>);
    expect(await screen.findByRole('heading', { name: 'Штаб СО КГЭУ «Тесла»' })).toBeTruthy();
    expect(await screen.findByText('Публикация')).toBeTruthy();
    const wikiLink = await screen.findByRole('link', { name: 'Алексей' });
    expect(wikiLink.getAttribute('href')).toBe('/wiki/people/example');
    expect(wikiLink.closest('tr')?.querySelectorAll('td')).toHaveLength(2);
    fireEvent.click(screen.getByRole('button', { name: 'Редактировать' }));
    fireEvent.change(screen.getByLabelText('Текст статьи в Markdown'), { target: { value: '# Черновик\n\nИзменение.' } });
    fireEvent.change(screen.getByLabelText('Причина изменения'), { target: { value: 'Исправлена формулировка' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    expect(await screen.findByText('Черновик сохранён. Публичная статья не менялась.')).toBeTruthy();
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith('/api/v1/editorial/draft') && init?.method === 'PUT')).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: 'Опубликовать' }));
    expect(await screen.findByText('Статья опубликована.')).toBeTruthy();
    expect(fetchMock.mock.calls.some(([input, init]) => String(input).endsWith('/api/v1/editorial/publish') && init?.method === 'POST')).toBe(true);
  });

  it('reloads the server version after an optimistic revision conflict', async () => {
    render(<AuthProvider><EditorialApp /></AuthProvider>);
    await screen.findByRole('heading', { name: 'Штаб СО КГЭУ «Тесла»' });
    fireEvent.click(screen.getByRole('button', { name: 'Редактировать' }));
    fireEvent.change(screen.getByLabelText('Текст статьи в Markdown'), { target: { value: '# Локальная правка\n\nНесохранённый текст.' } });
    fireEvent.change(screen.getByLabelText('Причина изменения'), { target: { value: 'Правка' } });
    draftConflict = true;
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    expect(await screen.findByText(/Версия на сервере изменилась/)).toBeTruthy();
    expect(articleReads).toBeGreaterThan(1);
    expect((screen.getByLabelText('Текст статьи в Markdown') as HTMLTextAreaElement).value).toContain('Несохранённый текст.');
    expect(screen.getByRole('button', { name: 'Оставить мой текст и продолжить' })).toBeTruthy();
  });

});
