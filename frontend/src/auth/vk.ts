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

export function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('VK bridge timeout')), ms)
    promise.then(
      (v) => {
        clearTimeout(timer)
        resolve(v)
      },
      (e) => {
        clearTimeout(timer)
        reject(e)
      },
    )
  })
}

export async function initVK(timeoutMs = 5000): Promise<void> {
  if (!isVK()) {
    return
  }
  await withTimeout(window.vkBridge!.send('VKWebAppInit'), timeoutMs)
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