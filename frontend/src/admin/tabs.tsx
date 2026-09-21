import type { JSX } from 'react'

import type { AdminTab } from './adminTypes'
import { ChatTab, DocsTab, GraphsTab, GroupsTab, KeysTab, PromptsTab, ProjectsTab } from './pages'

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
