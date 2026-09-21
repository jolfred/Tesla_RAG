import React, { useEffect } from 'react'

import { AuthProvider } from './auth/authContext'
import AdminApp from './admin/AdminApp'
import teslaFavicon from './assets/logos/tesla.jpg'
import LandingPage from './landing/LandingPage'

function isAdminPath(): boolean {
  return typeof window !== 'undefined' && window.location.pathname.startsWith('/admin')
}

function ThemedApp(): React.JSX.Element {
  useEffect(() => {
    document.body.classList.add('tesla-landing')
    // Фавиконка — настоящая эмблема штаба из бандла (а не буква).
    let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
    if (!link) {
      link = document.createElement('link')
      link.rel = 'icon'
      document.head.appendChild(link)
    }
    link.type = 'image/jpeg'
    link.href = teslaFavicon
    return () => document.body.classList.remove('tesla-landing')
  }, [])
  if (isAdminPath()) {
    return <AdminApp />
  }
  return <LandingPage />
}

export default function App(): React.JSX.Element {
  return (
    <AuthProvider>
      <ThemedApp />
    </AuthProvider>
  )
}
