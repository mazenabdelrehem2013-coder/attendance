/** Phase 16: audit log, tamper check, security monitoring, data retention. */

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'

export interface AuditLogItem {
  id: string
  seq: number
  created_at: string
  actor: string
  actor_name: string | null
  actor_role: string | null
  action: string
  object_type: string | null
  object_id: string | null
  changed: string[]
  ip_address: string | null
}

export interface AuditLogDetail extends AuditLogItem {
  old_value: Record<string, unknown> | null
  new_value: Record<string, unknown> | null
  user_agent: string | null
  request_id: string | null
  row_hash: string
  prev_hash: string | null
}

export interface ChainResult {
  ok: boolean
  rows_checked: number
  last_seq: number | null
  problem: string | null
  problem_seq: number | null
  checked_at: string
}

export interface AlertItem {
  id: string
  rule: string
  rule_label: string
  severity: Severity
  title: string
  details: Record<string, unknown>
  employee_id: string | null
  employee_name: string | null
  count: number
  first_seen_at: string
  last_seen_at: string
  status: 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED'
  handled_by: string | null
  handled_at: string | null
  note: string | null
}

export interface RuleInfo {
  rule: string
  label: string
  severity: Severity
  description: string
}

export interface CountItem {
  key: string
  label: string | null
  count: number
}

export interface SecurityOverview {
  date_from: string
  date_to: string
  total_events: number
  by_severity: Record<Severity, number>
  by_type: CountItem[]
  per_day: { date: string; low: number; medium: number; high: number; critical: number }[]
  top_employees: CountItem[]
  failed_logins: number
  locked_accounts: number
  top_ips: CountItem[]
  open_alerts: Record<Severity, number>
  chain: ChainResult | null
}

export interface RetentionItem {
  category: string
  label: string
  description: string
  retain_days: number
  min_days: number
  automatic: boolean
}

export const SEVERITY_COLOR: Record<Severity, 'default' | 'info' | 'warning' | 'error'> = {
  LOW: 'default',
  MEDIUM: 'info',
  HIGH: 'warning',
  CRITICAL: 'error',
}

export const EVENT_LABELS: Record<string, string> = {
  LOGIN_FAILED: 'Failed login',
  REFRESH_TOKEN_REUSE: 'Session token used twice',
  DEVICE_SHARED: 'Phone of another employee',
  MOCK_LOCATION: 'Fake-GPS app',
  INTEGRITY_FAIL: 'App/phone integrity failed',
  BAD_SIGNATURE: 'Not signed by the approved phone',
  REPLAY: 'Copied request',
  IMPOSSIBLE_TRAVEL: 'Impossible travel',
  OUTSIDE_GEOFENCE: 'Outside the office radius',
  CLOCK_SKEW: 'Phone clock changed',
  QR_INVALID: 'Invalid office QR',
  QR_MISSING: 'Office QR not scanned',
}

export const days = (n: number) => (n % 365 === 0 ? `${n / 365} year${n === 365 ? '' : 's'}` : `${n} days`)
