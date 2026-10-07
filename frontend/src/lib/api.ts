import { clearSession } from './session'

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
    public readonly requestId: string | null,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiJson<T>(
  path: string,
  init: RequestInit = {},
  authRequired = true,
): Promise<T> {
  const response = await apiRequest(path, init, authRequired)
  return (await response.json()) as T
}

async function apiRequest(path: string, init: RequestInit = {}, authRequired = true): Promise<Response> {
  const headers = new Headers(init.headers)
  const token = sessionStorage.getItem('marketmind_access_token')
  if (authRequired && token) headers.set('Authorization', `Bearer ${token}`)
  if (typeof init.body === 'string' && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(`/api/v1${path}`, { ...init, headers })
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null)
    const error = body && typeof body === 'object' ? body as Record<string, unknown> : {}
    const code = typeof error.code === 'string' ? error.code : 'HTTP_ERROR'
    const message = typeof error.message === 'string'
      ? error.message
      : response.status === 503 ? '服务暂时不可用，请稍后重试' : '请求失败，请稍后重试'
    const requestId = typeof error.request_id === 'string' ? error.request_id : null
    if (authRequired && response.status === 401) clearSession()
    throw new ApiError(response.status, code, message, requestId)
  }
  return response
}

export async function apiFile(path: string, filename: string): Promise<void> {
  const response = await apiRequest(path)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  try {
    link.click()
  } finally {
    URL.revokeObjectURL(url)
  }
}
