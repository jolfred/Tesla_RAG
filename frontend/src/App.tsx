import React, { useEffect } from 'react'

import { AuthProvider } from './auth/authContext'
import LandingPage from './landing/LandingPage'

function ThemedApp(): React.JSX.Element {
  useEffect(() => {
    document.body.classList.add('tesla-landing')
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
