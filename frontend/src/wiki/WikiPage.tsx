import React from 'react'

import teslaFavicon from '../assets/logos/tesla.jpg'
import WikiSection from './WikiSection'

/** Отдельная страница вики: /wiki (SPA-fallback отдаёт index.html). */
export default function WikiPage(): React.JSX.Element {
  return (
    <div style={{ background: '#07060A', minHeight: '100vh', color: '#F2EFFF' }}>
      <header style={{ maxWidth: 1120, margin: '0 auto', padding: '18px 20px 0', display: 'flex', alignItems: 'center', gap: 12 }}>
        <img src={teslaFavicon} alt="Логотип штаба Тесла" width={44} height={44} style={{ width: 44, height: 44, borderRadius: 12, objectFit: 'cover' }} />
        <span className="tesla-display" style={{ fontWeight: 700, fontSize: 17 }}>Тесла</span>
        <a href="/" style={{ marginLeft: 'auto', fontSize: 13, fontWeight: 700, color: '#D9CCFF', textDecoration: 'none', border: '1px solid rgba(255,255,255,0.16)', borderRadius: 999, padding: '8px 16px' }}>
          ← На главную
        </a>
      </header>
      <WikiSection />
    </div>
  )
}
