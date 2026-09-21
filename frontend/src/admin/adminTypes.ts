// Изолированный модуль админки: зависит только от auth/token.
// При выносе в отдельный деплой копируется целиком папкой src/admin
// (+ один файл auth/token.ts), меняется только baseURL в adminClient.

export type AdminTab =
  | 'docs'
  | 'groups'
  | 'projects'
  | 'chat'
  | 'prompts'
  | 'graphs'
  | 'keys'

export interface AdminProject {
  slug: string
  name: string
  description: string
  created_at: string
}

export interface AdminStatus {
  status: string
  projects_count: number
  jobs_active: number
}

export const ADMIN_TABS: { id: AdminTab; title: string; hint: string }[] = [
  { id: 'docs', title: 'Документы', hint: 'Загрузка и список (шаг 1)' },
  { id: 'groups', title: 'VK-группы', hint: 'Парсер и статусы (шаг 2)' },
  { id: 'projects', title: 'Проекты', hint: 'Группировка и индексация (шаг 3)' },
  { id: 'chat', title: 'Тест чата', hint: 'Проверка ответов (шаг 4)' },
  { id: 'prompts', title: 'Промпты', hint: 'Редактор промптов (шаг 5)' },
  { id: 'graphs', title: 'Графы', hint: 'Ссылки и просмотр (шаг 6)' },
  { id: 'keys', title: 'Ключи', hint: 'API-ключи без рестарта (шаг 7)' },
]
