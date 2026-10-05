import type { Role, TeamSummary } from './types'

export interface GroupCount {
  name: string
  employees: number
  present: number
  late: number
  absent: number
  pending_review: number
  on_leave: number
}

export interface HrOverview {
  date: string
  summary: TeamSummary
  suspicious_attempts: number
  rejected_attempts: number
  pending_reviews_total: number
  by_location: GroupCount[]
  by_department: GroupCount[]
}

export interface TrendPoint {
  date: string
  present: number
  late: number
  absent: number
  pending_review: number
  on_leave: number
  attendance_rate: number | null
}

export interface ReviewItem {
  event_id: string
  employee_id: string
  employee_code: string
  employee_name: string
  event_type: 'CHECK_IN' | 'CHECK_OUT'
  server_time: string
  result: 'ACCEPTED' | 'FLAGGED' | 'REJECTED'
  reason_code: string | null
  location: string | null
  distance_m: number | null
  accuracy_m: number | null
  risk_score: number | null
  failed_checks: string[]
  review_decision: 'APPROVED' | 'REJECTED' | null
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string | null
}

export interface ReviewDetail extends ReviewItem {
  latitude: number | null
  longitude: number | null
  fix_age_ms: number | null
  device_reported_at: string | null
  app_version: string | null
  device_model: string | null
  device_status: string | null
  checks: Record<string, string>
  details: Record<string, Record<string, unknown>>
  policy: Record<string, unknown>
  security_events: { type: string; severity: string; details: Record<string, unknown>; at: string }[]
}

export interface Page<T> {
  items: T[]
  total: number
}

export interface SecurityEvent {
  id: string
  created_at: string
  event_type: string
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
  employee_code: string | null
  employee_name: string | null
  attendance_event_id: string | null
  details: Record<string, unknown>
}

export interface Ref {
  id: string
  name: string
}

export interface Employee {
  id: string
  user_id: string
  employee_code: string
  full_name: string
  email: string
  phone: string | null
  role: Role
  is_active: boolean
  employment_status: 'ACTIVE' | 'SUSPENDED' | 'TERMINATED'
  hire_date: string | null
  department: Ref | null
  manager: Ref | null
  work_schedule_id: string | null
  locations: { location_id: string; name: string; is_primary: boolean }[]
}

export interface ManagerOption {
  id: string
  name: string
  email: string
  team_size: number
}

export interface Location {
  id: string
  branch_id: string
  name: string
  code: string
  address: string | null
  latitude: string
  longitude: string
  radius_m: number
  timezone: string
  work_schedule_id: string | null
  is_active: boolean
}

export interface Department {
  id: string
  name: string
  code: string
  branch_id: string | null
  is_active: boolean
}

export interface Branch {
  id: string
  name: string
  code: string
  is_active: boolean
}

export interface ScheduleDay {
  weekday: number
  start_time: string
  end_time: string
}

export interface Schedule {
  id: string
  name: string
  grace_minutes: number
  early_departure_minutes: number
  is_active: boolean
  days: ScheduleDay[]
}

export interface Device {
  id: string
  employee_id: string
  employee_name: string
  employee_code: string
  status: string
  device_model: string | null
  os_version: string | null
  app_version: string | null
  requested_at: string
  approved_at: string | null
  decision_note: string | null
  last_seen_at: string | null
}

export interface QrDisplay {
  id: string
  location_id: string
  location_name: string
  display_label: string
  rotation_seconds: number
  is_active: boolean
  last_heartbeat_at: string | null
  display_key?: string
}

export type PolicyAction = 'ALLOW' | 'FLAG' | 'REJECT'

export interface Policy {
  location_id: string | null
  location_name: string | null
  verification_mode: 'GPS_ONLY' | 'GPS_QR' | 'GPS_QR_PLUS'
  on_mock_location: PolicyAction
  on_integrity_fail: PolicyAction
  on_poor_accuracy: PolicyAction
  on_stale_location: PolicyAction
  on_outside_geofence: PolicyAction
  on_impossible_travel: PolicyAction
  on_clock_skew: PolicyAction
  on_qr_fail: PolicyAction
  max_accuracy_m: number
  max_fix_age_s: number
  challenge_ttl_s: number
  max_travel_speed_kmh: number
  max_clock_skew_s: number
  flagged_counts_before_review: boolean
}

export interface Holiday {
  id: string
  holiday_date: string
  name: string
  location_id: string | null
}

export interface Leave {
  id: string
  employee_id: string
  employee_name: string
  leave_type: string
  start_date: string
  end_date: string
  status: 'APPROVED' | 'CANCELLED'
  note: string | null
}

/** Human labels for the reasons HR sees. */
export const REASONS: Record<string, string> = {
  OUTSIDE_LOCATION: 'Outside the office radius',
  POOR_ACCURACY: 'GPS signal too weak',
  STALE_LOCATION: 'Old GPS reading',
  MOCK_LOCATION: 'Fake-GPS app detected',
  INTEGRITY_FAIL: 'App/phone integrity check failed',
  INTEGRITY_MISSING: 'No integrity token',
  IMPOSSIBLE_TRAVEL: 'Impossible travel speed',
  CLOCK_SKEW: 'Phone clock changed',
  QR_INVALID: 'Invalid or expired office QR',
  QR_MISSING: 'Office QR not scanned',
  MULTIPLE_WARNINGS: 'Several small doubts together',
  BAD_SIGNATURE: 'Request not signed by the approved phone',
  NO_DEVICE_KEY: 'Phone has no security key',
  REPLAY: 'Re-used request (possible copy)',
  CHALLENGE_EXPIRED: 'Request expired',
  CHALLENGE_UNKNOWN: 'Unknown request code',
  CHALLENGE_MISMATCH: 'Request code mismatch',
  ALREADY_CHECKED_IN: 'Already checked in',
  NOT_CHECKED_IN: 'Check-out without check-in',
  NO_ASSIGNED_LOCATION: 'No assigned location',
}

export const CHECKS: Record<string, string> = {
  replay_check: 'One-time code',
  device_check: 'Phone signature',
  geofence: 'Distance to office',
  gps_accuracy: 'GPS accuracy',
  location_age: 'Age of GPS reading',
  mock_location: 'Fake-GPS flag',
  play_integrity: 'Play Integrity',
  timestamp_check: 'Phone clock',
  movement_check: 'Travel speed',
  qr_check: 'Office QR',
}
