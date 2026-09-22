import React from 'react'

import teslaFavicon from '../assets/logos/tesla.jpg'
import WikiArticle from './WikiArticle'
import WikiCatalog from './WikiCatalog'

/** Отдельная страница вики: /wiki — каталог, /wiki/<slug> — статья. Светлая «бумага». */
export default function WikiPage(): React.JSX.Element {
  const m = window.location.pathname.match(/^\/wiki\/(.+?)\/?$/)
  const slug = m ? decodeURIComponent(m[1]) : ''
  return (
    <div style={{ background: '#FAF7F1', minHeight: '100vh', color: '#211B16' }}>
      <header style={{ maxWidth: 1120, margin: '0 auto', padding: '18px 20px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
        <img src={teslaFavicon} alt="Логотип штаба Тесла" width={44} height={44} style={{ width: 44, height: 44, borderRadius: 12, objectFit: 'cover' }} />
        <span className="tesla-display" style={{ fontWeight: 700, fontSize: 17, color: '#211B16' }}>Тесла · Летопись</span>
        <a href="/" style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: '#6D28D9', textDecoration: 'none', border: '1px solid #E7DFD2', background: '#fff', borderRadius: 999, padding: '8px 16px' }}>
          ← На главную
        </a>
      </header>
      {slug ? <WikiArticle slug={slug} /> : <WikiCatalog />}
    </div>
  )
}
