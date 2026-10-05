import type { JSX } from 'react'

import type { AdminTab } from './adminTypes'
import { ChatTab, DocsTab, GroupsTab, KeysTab, PromptsTab, ProjectsTab, QueueTab } from './pages'
import WikiGraphTab from './WikiGraphTab'

export function tabContent(tab: AdminTab): JSX.Element {
  switch (tab) {
    case 'docs':
      return <DocsTab />
    case 'groups':
      return <GroupsTab />
    case 'queue':
      return <QueueTab />
    case 'projects':
      return <ProjectsTab />
    case 'chat':
      return <ChatTab />
    case 'prompts':
      return <PromptsTab />
    case 'wiki-graph':
      return <WikiGraphTab />
    case 'keys':
      return <KeysTab />
  }
}
