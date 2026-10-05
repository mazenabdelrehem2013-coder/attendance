import Chip from '@mui/material/Chip'

import type { TeamRow } from '../api/types'

const STATUS: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'secondary' | 'default' | 'info' }> = {
  PRESENT: { label: 'Present', color: 'success' },
  LATE: { label: 'Late', color: 'warning' },
  PENDING_REVIEW: { label: 'Pending review', color: 'secondary' },
  NOT_CHECKED_IN: { label: 'Not checked in', color: 'default' },
  ABSENT: { label: 'Absent', color: 'error' },
  ON_LEAVE: { label: 'On leave', color: 'info' },
  HOLIDAY: { label: 'Holiday', color: 'info' },
  NON_WORKING_DAY: { label: 'Day off', color: 'default' },
}

export function StatusChip({ row }: { row: TeamRow }) {
  const s = STATUS[row.status] ?? { label: row.status, color: 'default' as const }
  return <Chip size="small" label={s.label} color={s.color} variant={row.status === 'NOT_CHECKED_IN' ? 'outlined' : 'filled'} />
}

export function DepartureChip({ row }: { row: TeamRow }) {
  if (row.checked_in_now) return <Chip size="small" label="Checked in" color="success" variant="outlined" />
  if (row.departure_status === 'MISSING_CHECKOUT') return <Chip size="small" label="Missing check-out" color="error" variant="outlined" />
  if (row.departure_status === 'EARLY_DEPARTURE') return <Chip size="small" label="Left early" color="warning" variant="outlined" />
  return null
}

export function VerificationChip({ value }: { value: string | null }) {
  if (value === 'VERIFIED') return <Chip size="small" label="Verified" color="success" variant="outlined" />
  if (value === 'PENDING_REVIEW') return <Chip size="small" label="Pending review" color="secondary" variant="outlined" />
  return <>—</>
}
