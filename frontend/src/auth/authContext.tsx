import React, { createContext, useContext, useEffect, useMemo, useState } from 'react'

import { ApiClient, ApiError, api } from '../api/client'
import type { Role } from '../types'
import { clearToken, loadToken, saveToken } from './token'
import { getLaunchParams, initVK, isVK } from './vk'

export type AuthStatus = 'loading' | 'ready'

export interface AuthState {
  status: AuthStatus
  role: Role | null
  vkUserId: string | null
  expiresAt: string | null
  isVK: boolean
}

interface AuthContextValue {
  state: AuthState
  loginAdmin: (apiKey: string) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

function applySession(resp: {
  role: Role
  vk_user_id: string | null
  expires_at: string
}, token: string, client: ApiClient, setState: (s: AuthState) => void): void {
  client.setToken(token)
  saveToken(token)
  setState({
    status: 'ready',
    role: resp.role,
    vkUserId: resp.vk_user_id,
    expiresAt: resp.expires_at,
    isVK: isVK(),
  })
}

export function AuthProvider({ children }: { children: React.ReactNode }): React.JSX.Element {
  const [state, setState] = useState<AuthState>({
    status: 'loading',
    role: null,
    vkUserId: null,
    expiresAt: null,
    isVK: false,
  })

  const refreshGuest = async (): Promise<void> => {
    const resp = await api.guest()
    api.setToken(resp.token)
    saveToken(resp.token)
    setState({
      status: 'ready',
      role: resp.role,
      vkUserId: resp.vk_user_id,
      expiresAt: resp.expires_at,
      isVK: isVK(),
    })
  }

  useEffect(() => {
    api.setRefresh(refreshGuest)

    const bootstrap = async (): Promise<void> => {
      try {
        const saved = loadToken()
        if (saved) {
          api.setToken(saved)
          try {
            const me = await api.me()
            setState({
              status: 'ready',
              role: me.role,
              vkUserId: me.vk_user_id,
              expiresAt: me.expires_at,
              isVK: isVK(),
            })
            return
          } catch (e) {
            if (e instanceof ApiError && e.status === 401) {
              // Токен истёк/отозван — тихая перевыдача гостя (FR-1.3)
              await refreshGuest()
              return
            }
            throw e
          }
        }

        // Нет токена: пробуем VK-вход (если сконфигурирован), иначе гость (FR-2.5)
        if (isVK()) {
          try {
            await initVK()
            const lp = getLaunchParams()
            if (lp) {
              const resp = await api.vk(lp)
              applySession(resp, resp.token, api, setState)
              return
            }
          } catch {
            // 501 (не сконфигурирован) / 401 (подпись) / сеть -> fallback на гостя
          }
        }
        await refreshGuest()
      } catch (e) {
        // Неустранимая ошибка инициализации — очищаем токен, остаёмся «гостем без сессии»
        console.error('Auth bootstrap failed', e)
        clearToken()
        api.setToken(null)
        setState({
          status: 'ready',
          role: null,
          vkUserId: null,
          expiresAt: null,
          isVK: isVK(),
        })
      }
    }

    void bootstrap()
  }, [])

  const loginAdmin = async (apiKey: string): Promise<void> => {
    const resp = await api.admin({ api_key: apiKey })
    applySession(resp, resp.token, api, setState)
  }

  const logout = async (): Promise<void> => {
    try {
      await api.logout()
    } catch {
      // токен уже невалиден — всё равно очищаем
    }
    clearToken()
    api.setToken(null)
    await refreshGuest()
  }

  const value = useMemo<AuthContextValue>(() => ({ state, loginAdmin, logout }), [state])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider')
  }
  return ctx
}