import { loadToken } from '../auth/token';

export class EditorialError extends Error {
  constructor(public status: number, message: string) { super(message); this.name = 'EditorialError'; }
}
async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers); headers.set('Content-Type', 'application/json');
  const token = loadToken(); if (token) headers.set('Authorization', `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`/api/v1/editorial${path}`, { ...init, headers }); } catch { throw new EditorialError(0, 'Не удалось связаться с сервером.'); }
  if (!response.ok) { let msg = `Ошибка ${response.status}`; try { msg = ((await response.json()) as { detail?: string ;}).detail || msg; } catch { /* keep status */ } throw new EditorialError(response.status, msg); }
  return (await response.json()) as T;
}
export interface EditorialArticleSummary { slug: string; title: string; kind: string; revision: string; status: string; has_draft: boolean; updated_at: string; }
export interface EditorialSource { url: string; title: string; group_name: string; published_at: string; }
export interface EditorialDraft { markdown: string; base_revision: string; revision: string; updated_at: string; }
export interface EditorialArticle { slug: string; title: string; markdown: string; revision: string; sources: EditorialSource[]; draft: EditorialDraft | null; }
export interface EditorialVersion { id: string; created_at: string; actor: string; reason: string; sha256: string; kind: string; is_current: boolean; publication_state?: 'published' | 'pending'; }
export interface EditorialComment { id: string; text: string; actor: string; created_at: string; }
export type DiscussionStatus = 'waiting_editor' | 'waiting_curator' | 'resolved';
export type DiscussionCategory = 'curator_question' | 'source_conflict' | 'editorial_note';
export interface EditorialDiscussion { id: string; page: string; title: string; original_text: string; category: DiscussionCategory; status: DiscussionStatus; owner: string | null; resolution: string | null; created_at: string; updated_at: string; comments: EditorialComment[]; }
export const editorialApi = {
  sourceExcerpt: (body: { item_id: string; line_start: number; line_end: number ;}) => request<{ url: string; reference: string; title: string; markdown_citation: string ;}>('/source-excerpts', { method: 'POST', body: JSON.stringify(body) }),
  articles: (q = '') => request<{ articles: EditorialArticleSummary[] ;}>(`/articles?q=${encodeURIComponent(q)}`),
  article: (slug: string) => request<EditorialArticle>(`/article?slug=${encodeURIComponent(slug)}`),
  saveDraft: (body: { slug: string; markdown: string; expected_revision: string; expected_draft_revision: string | null; reason?: string ;}) => request<{ ok: true; draft: EditorialDraft ;}>('/draft', { method: 'PUT', body: JSON.stringify(body) }),
  publish: (body: { slug: string; markdown: string; expected_revision: string; reason: string ;}) => request<{ ok: true; slug: string; revision: string ;}>('/publish', { method: 'POST', body: JSON.stringify(body) }),
  history: (slug: string) => request<{ versions: EditorialVersion[] ;}>(`/history?slug=${encodeURIComponent(slug)}`),
  version: (slug: string, id: string) => request<EditorialVersion & { markdown: string ;}>(`/history/${encodeURIComponent(id)}?slug=${encodeURIComponent(slug)}`),
  restore: (body: { slug: string; version_id: string; expected_revision: string; reason: string ;}) => request<{ ok: true; slug: string; revision: string ;}>('/restore', { method: 'POST', body: JSON.stringify(body) }),
  discussions: (slug?: string, status?: DiscussionStatus) => { const q = new URLSearchParams(); if (slug) q.set('slug', slug); if (status) q.set('status', status); return request<{ discussions: EditorialDiscussion[] ;}>(`/discussions${q.size ? `?${q}` : ''}`) ;},
  createDiscussion: (body: { page: string; title: string; text: string; category?: DiscussionCategory; owner?: string ;}) => request<{ discussion: EditorialDiscussion ;}>('/discussions', { method: 'POST', body: JSON.stringify(body) }),
  updateDiscussion: (id: string, body: { status?: DiscussionStatus; owner?: string; resolution?: string; expected_updated_at: string ;}) => request<{ discussion: EditorialDiscussion ;}>(`/discussions/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  addComment: (id: string, text: string) => request<{ discussion: EditorialDiscussion ;}>(`/discussions/${encodeURIComponent(id)}/comments`, { method: 'POST', body: JSON.stringify({ text }) }),
};
