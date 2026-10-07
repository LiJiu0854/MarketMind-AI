export type Role = 'admin' | 'operator' | 'analyst'
export interface User {
  id: number
  email: string
  full_name: string
  role: Role
  is_active: boolean
  created_at: string
  updated_at: string
}
export interface UserCreate { email: string; full_name: string; password: string; role: Role }
export type UserUpdate = Partial<UserCreate & Pick<User, 'is_active'>>
