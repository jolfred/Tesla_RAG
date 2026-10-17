import React, { useEffect, useState } from 'react'
import { useAuth } from '../auth/authContext'
import './admin.css'
import { ADMIN_TABS, type AdminTab } from './adminTypes'
import { tabContent } from './tabs'
import { AdminLogin } from './AdminGate'

function tabFromUrl():AdminTab {const seg=window.location.pathname.split('/')[2];return ADMIN_TABS.some(t=>t.id===seg)?seg as AdminTab:'overview'}
export default function AdminApp():React.JSX.Element {
 const {state,logout}=useAuth();const[tab,setTab]=useState<AdminTab>(tabFromUrl)
 useEffect(()=>{document.body.classList.remove('tesla-landing')},[])
 useEffect(()=>{window.history.replaceState(null,'',`/admin/${tab}`)},[tab])
 if(state.status==='loading')return <div className="tesla-admin"><main className="ta-main">Загрузка…</main></div>
 if(state.role!=='admin')return <AdminLogin/>
 const active=ADMIN_TABS.find(t=>t.id===tab)??ADMIN_TABS[0]
 return <div className="tesla-admin"><div className="ta-shell"><aside className="ta-side"><a className="ta-logo" href="/admin/overview">Тесла · Администрирование<small>Операционная панель</small></a><nav className="ta-nav" aria-label="Администрирование">{ADMIN_TABS.map(t=><button key={t.id} className={tab===t.id?'active':''} onClick={()=>setTab(t.id)}>{t.title}</button>)}</nav><nav className="ta-nav ta-nav-bottom"><a href="/editorial">Редакция Wiki</a><button onClick={()=>void logout()}>Выйти</button></nav></aside><main className="ta-main"><header className="ta-pagehead"><div><h1 className="ta-title">{active.title}</h1><p className="ta-muted">{active.hint}</p></div><a href="/editorial">Открыть редакцию →</a></header>{tabContent(tab)}</main></div></div>
}
