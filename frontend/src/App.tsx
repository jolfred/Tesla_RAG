import React, { useEffect } from 'react'

import { AuthProvider } from './auth/authContext'
import teslaFavicon from './assets/logos/tesla.jpg'
import LandingPage from './landing/LandingPage'

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
  return <LandingPage />
}

export default function App(): React.JSX.Element {
  return (
    <AuthProvider>
      <ThemedApp />
    </AuthProvider>
  )
}
