import type { JSX } from 'react'

import type { AdminTab } from './adminTypes'
import { ChatTab, DocsTab, GroupsTab, PromptsTab, ProjectsTab } from './pages'

// Заглушки шагов 2–7: каждый таб заменяется полноценной страницей
// своим шагом, интерфейс AdminApp не меняется.
function Stub({ text }: { text: string }): JSX.Element {
  return (
    <div className="ta-card">
      <p className="ta-muted">{text}</p>
    </div>
  )
}

export function GraphsTab(): JSX.Element {
  return <Stub text="Шаг 6: ссылки на графы после индексации." />
}

export function KeysTab(): JSX.Element {
  return <Stub text="Шаг 7: API-ключи LLM и VK без рестарта." />
}

export function tabContent(tab: AdminTab): JSX.Element {
  switch (tab) {
    case 'docs':
      return <DocsTab />
    case 'groups':
      return <GroupsTab />
    case 'projects':
      return <ProjectsTab />
    case 'chat':
      return <ChatTab />
    case 'prompts':
      return <PromptsTab />
    case 'graphs':
      return <GraphsTab />
    case 'keys':
      return <KeysTab />
  }
}
