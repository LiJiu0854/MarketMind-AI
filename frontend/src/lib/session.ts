import { ref } from 'vue'
import { ApiError, apiJson } from './api'
import type { User } from '../features/users/types'

const tokenKey = 'marketmind_access_token'
export const currentUser = ref<User | null>(null)

export function readToken(): string | null { return sessionStorage.getItem(tokenKey) }
export function saveToken(token: string): void { sessionStorage.setItem(tokenKey, token) }
export function setCurrentUser(user: User | null): void { currentUser.value = user }
export function clearSession(): void {
  sessionStorage.removeItem(tokenKey)
  currentUser.value = null
}

export async function restoreSession(): Promise<boolean> {
  if (!readToken()) return false
  try {
    setCurrentUser(await apiJson<User>('/auth/me'))
    return true
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return false
    throw error
  }
}
