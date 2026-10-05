// Изолированный модуль админки: зависит только от auth/token.
// При выносе в отдельный деплой копируется целиком папкой src/admin
// (+ один файл auth/token.ts), меняется только baseURL в adminClient.

export type AdminTab =
  | 'docs'
  | 'groups'
  | 'queue'
  | 'projects'
  | 'chat'
  | 'prompts'
  | 'wiki-graph'
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
  { id: 'groups', title: 'VK-группы', hint: 'Группы, спарсенное, кнопки «в очередь»' },
  { id: 'queue', title: 'Очередь', hint: 'Что запускать, куда и с какими параметрами' },
  { id: 'projects', title: 'Проекты', hint: 'Группировка материалов; поиск пока работает по Летописи' },
  { id: 'chat', title: 'Тест чата', hint: 'Проверка ответов по Летописи' },
  { id: 'prompts', title: 'Промпты', hint: 'Редактор промптов' },
  { id: 'wiki-graph', title: 'Граф Wiki', hint: 'Статьи Летописи и ссылки между ними' },
  { id: 'keys', title: 'Ключи', hint: 'API-ключи без рестарта' },
]
