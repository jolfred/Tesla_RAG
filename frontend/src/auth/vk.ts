declare global {
  interface Window {
    vkBridge?: {
      send: (method: string, params?: Record<string, unknown>) => Promise<unknown>
    }
  }
}

export function isVK(): boolean {
  return typeof window !== 'undefined' && !!window.vkBridge
}

export async function initVK(): Promise<void> {
  if (!isVK()) {
    return
  }
  await window.vkBridge!.send('VKWebAppInit')
}

export interface VKLaunchParams {
  params: Record<string, string>
  sign: string
}

/**
 * Извлекает launch-параметры VK Mini App из query-строки (FR-2.5).
 * URLSearchParams уже декодирует значения; sign передаётся как есть.
 */
export function getLaunchParams(): VKLaunchParams | null {
  if (typeof window === 'undefined') {
    return null
  }
  const qs = window.location.search
  if (!qs) {
    return null
  }
  const usp = new URLSearchParams(qs)
  const params: Record<string, string> = {}
  let sign = ''
  usp.forEach((value, key) => {
    if (key === 'sign') {
      sign = value
      return
    }
    params[key] = value
  })
  if (!sign) {
    return null
  }
  return { params, sign }
}