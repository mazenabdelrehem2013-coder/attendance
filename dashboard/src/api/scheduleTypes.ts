/** Phase 15: alerts (bell), scheduled reports and ready-to-download report files. */

export type RecipientRole = 'HR' | 'MANAGER' | 'ADMIN'

export interface NotificationItem {
  id: string
  event: string
  title: string
  body: string
  link: string | null
  created_at: string
  read: boolean
}

export interface NotificationList {
  items: NotificationItem[]
  unread: number
}

export interface ScheduleInput {
  name: string
  report: 'daily' | 'weekly' | 'monthly' | 'late' | 'absence' | 'suspicious'
  frequency: 'daily' | 'weekly' | 'monthly'
  time: string
  days: number[]
  weekday: number
  day_of_month: number
  daily_period: 'today' | 'previous'
  formats: ('EXCEL' | 'PDF')[]
  recipient_roles: RecipientRole[]
  location_id: string | null
  department_id: string | null
  is_enabled: boolean
}

export interface Schedule extends ScheduleInput {
  id: string
  description: string
  next_run_at: string | null
  last_run_at: string | null
  timezone: string
}

export interface AlertSetting {
  event: string
  label: string
  description: string
  enabled: boolean
  roles: RecipientRole[]
  thresholds: Record<string, number>
}

export interface ReadyReport {
  id: string
  title: string
  period: string
  scope: string
  schedule_name: string | null
  format: 'EXCEL' | 'PDF'
  filename: string
  size_bytes: number
  rows: number | null
  created_at: string
}

export interface ReadyReportList {
  items: ReadyReport[]
  total: number
  keep_days: number
}

export const REPORT_LABELS: Record<ScheduleInput['report'], string> = {
  daily: 'Daily attendance',
  weekly: 'Weekly attendance',
  monthly: 'Monthly attendance',
  late: 'Late arrivals',
  absence: 'Absences',
  suspicious: 'Suspicious attendance',
}

export const ROLE_LABELS: Record<RecipientRole, string> = {
  HR: 'HR',
  MANAGER: 'Managers (own team)',
  ADMIN: 'Admins',
}

export const DAY_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
