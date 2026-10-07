import { apiJson } from '../../lib/api'
import type { Page } from '../../lib/types'
import type { User, UserCreate, UserUpdate } from './types'

export const listUsers = (page: number) => apiJson<Page<User>>(`/users?page=${page}`)
export const createUser = (input: UserCreate, idempotencyKey: string) => apiJson<User>('/users', {
  method: 'POST', headers: { 'Idempotency-Key': idempotencyKey }, body: JSON.stringify(input),
})
export const updateUser = (id: number, input: UserUpdate) => apiJson<User>(`/users/${id}`, {
  method: 'PATCH', body: JSON.stringify(input),
})
export const deactivateUser = (id: number) => apiJson<User>(`/users/${id}`, { method: 'DELETE' })
