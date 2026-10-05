export type Role = 'EMPLOYEE' | 'MANAGER' | 'HR' | 'ADMIN'

export interface UserSummary {
  id: string
  email: string
  role: Role
  must_change_password: boolean
  employee: { id: string; employee_code: string; full_name: string } | null
}

export interface TokenResponse {
  access_token: string
  expires_in: number
  user: UserSummary
}

export type TeamStatus =
  | 'PRESENT'
  | 'LATE'
  | 'PENDING_REVIEW'
  | 'NOT_CHECKED_IN'
  | 'ABSENT'
  | 'ON_LEAVE'
  | 'HOLIDAY'
  | 'NON_WORKING_DAY'

export interface TeamRow {
  employee_id: string
  employee_code: string
  full_name: string
  department: string | null
  location: string | null
  check_in: string | null
  check_out: string | null
  worked_minutes: number
  status: TeamStatus
  arrival_status: string | null
  departure_status: string | null
  checked_in_now: boolean
  verification_status: string | null
  note: string | null
}

export interface TeamSummary {
  total_employees: number
  present: number
  late: number
  absent: number
  not_checked_in: number
  checked_in_now: number
  missing_checkout: number
  suspicious: number
  on_leave: number
}

export interface TeamAttendance {
  date: string
  generated_at: string
  summary: TeamSummary
  rows: TeamRow[]
}

export interface NamedItem {
  id: string
  name: string
  is_active: boolean
}
