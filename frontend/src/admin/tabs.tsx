import type { JSX } from 'react'
import type { AdminTab } from './adminTypes'
import { AdminOverviewTab, AdminMaterialsTab, AdminSourcesTab, AdminTasksTab, AdminInstructionsTab } from './operations'
export function tabContent(tab:AdminTab):JSX.Element {
 switch(tab){case'overview':return <AdminOverviewTab/>;case'materials':return <AdminMaterialsTab/>;case'sources':return <AdminSourcesTab/>;case'tasks':return <AdminTasksTab/>;case'instructions':return <AdminInstructionsTab/>}
}
