import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Divider from '@mui/material/Divider'
import Drawer from '@mui/material/Drawer'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { apiGet, apiPost, ApiError } from '../../api/client'
import { CHECKS, REASONS, type Page, type ReviewDetail, type ReviewItem, type SecurityEvent } from '../../api/hrTypes'
import { useCurrentUser } from '../../auth/AuthProvider'

type TabKey = 'PENDING' | 'REVIEWED' | 'REJECTED_ATTEMPTS' | 'SECURITY'

const dateTime = (iso: string) =>
  new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(new Date(iso))

const SIGNAL_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  PASS: 'success', WARN: 'warning', FAIL: 'error', NOT_APPLICABLE: 'default',
}

export function ReviewPage() {
  const [tab, setTab] = useState<TabKey>('PENDING')
  const [selected, setSelected] = useState<string | null>(null)

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Suspicious activity</Typography>
      <Typography color="text.secondary">
        Flagged check-ins and check-outs don't count until you approve them. Employees only see
        "waiting for HR review" – the reasons below are for HR only.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="PENDING" label="Waiting for review" />
        <Tab value="REVIEWED" label="Reviewed" />
        <Tab value="REJECTED_ATTEMPTS" label="Rejected attempts" />
        <Tab value="SECURITY" label="Security events" />
      </Tabs>
      {tab === 'SECURITY' ? <SecurityEvents onOpen={setSelected} /> : <ReviewTable state={tab} onOpen={setSelected} />}
      <ReviewDrawer eventId={selected} onClose={() => setSelected(null)} />
    </Stack>
  )
}

function ReviewTable({ state, onOpen }: { state: Exclude<TabKey, 'SECURITY'>; onOpen: (id: string) => void }) {
  const items = useQuery({
    queryKey: ['review', state],
    queryFn: () => apiGet<Page<ReviewItem>>('/hr/review', { state, limit: '200' }),
  })
  if (items.error) return <Alert severity="error">{(items.error as Error).message}</Alert>
  return (
    <Paper variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow>
            <TableCell>When</TableCell>
            <TableCell>Employee</TableCell>
            <TableCell>Action</TableCell>
            <TableCell>Location</TableCell>
            <TableCell>Reason</TableCell>
            <TableCell>Distance</TableCell>
            <TableCell>Risk</TableCell>
            {state === 'REVIEWED' && <TableCell>Decision</TableCell>}
          </TableRow>
        </TableHead>
        <TableBody>
          {items.data?.items.map((i) => (
            <TableRow key={i.event_id} hover sx={{ cursor: 'pointer' }} onClick={() => onOpen(i.event_id)}>
              <TableCell>{dateTime(i.server_time)}</TableCell>
              <TableCell>{i.employee_name} <Typography component="span" color="text.secondary">({i.employee_code})</Typography></TableCell>
              <TableCell>{i.event_type === 'CHECK_IN' ? 'Check-in' : 'Check-out'}</TableCell>
              <TableCell>{i.location ?? '—'}</TableCell>
              <TableCell>{REASONS[i.reason_code ?? ''] ?? i.reason_code ?? '—'}</TableCell>
              <TableCell>{i.distance_m != null ? `${Math.round(i.distance_m)} m` : '—'}</TableCell>
              <TableCell>{i.risk_score ?? '—'}</TableCell>
              {state === 'REVIEWED' && (
                <TableCell>
                  <Chip size="small" label={i.review_decision === 'APPROVED' ? 'Approved' : 'Rejected'}
                    color={i.review_decision === 'APPROVED' ? 'success' : 'error'} />
                </TableCell>
              )}
            </TableRow>
          ))}
          {items.data?.items.length === 0 && (
            <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
              {state === 'PENDING' ? 'Nothing is waiting for review. 🎉' : 'Nothing here.'}
            </TableCell></TableRow>
          )}
        </TableBody>
      </Table>
    </Paper>
  )
}

function SecurityEvents({ onOpen }: { onOpen: (id: string) => void }) {
  const events = useQuery({ queryKey: ['security-events'], queryFn: () => apiGet<Page<SecurityEvent>>('/security-events', { limit: '200' }) })
  return (
    <Paper variant="outlined">
      <Table size="small">
        <TableHead>
          <TableRow><TableCell>When</TableCell><TableCell>Type</TableCell><TableCell>Severity</TableCell><TableCell>Employee</TableCell><TableCell>Details</TableCell></TableRow>
        </TableHead>
        <TableBody>
          {events.data?.items.map((e) => (
            <TableRow key={e.id} hover sx={{ cursor: e.attendance_event_id ? 'pointer' : undefined }}
              onClick={() => e.attendance_event_id && onOpen(e.attendance_event_id)}>
              <TableCell>{dateTime(e.created_at)}</TableCell>
              <TableCell>{e.event_type}</TableCell>
              <TableCell><Chip size="small" label={e.severity}
                color={e.severity === 'HIGH' || e.severity === 'CRITICAL' ? 'error' : e.severity === 'MEDIUM' ? 'warning' : 'default'} /></TableCell>
              <TableCell>{e.employee_name ?? '—'}</TableCell>
              <TableCell sx={{ fontFamily: 'monospace', fontSize: 12 }}>{JSON.stringify(e.details)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  )
}

function ReviewDrawer({ eventId, onClose }: { eventId: string | null; onClose: () => void }) {
  const me = useCurrentUser()
  const queryClient = useQueryClient()
  const [note, setNote] = useState('')
  const detail = useQuery({
    queryKey: ['review-detail', eventId],
    queryFn: () => apiGet<ReviewDetail>(`/hr/review/${eventId}`),
    enabled: !!eventId,
  })
  const decide = useMutation({
    mutationFn: (decision: 'APPROVED' | 'REJECTED') => apiPost(`/hr/review/${eventId}`, { decision, note: note || null }),
    onSuccess: () => {
      setNote('')
      queryClient.invalidateQueries()
      onClose()
    },
  })
  const d = detail.data
  const ownRecord = d && me.employee?.id === d.employee_id

  return (
    <Drawer anchor="right" open={!!eventId} onClose={onClose}>
      <Box sx={{ width: 480, p: 3 }}>
        {!d ? <Typography>Loading…</Typography> : (
          <Stack spacing={2}>
            <Typography variant="h6">{d.employee_name} – {d.event_type === 'CHECK_IN' ? 'check-in' : 'check-out'}</Typography>
            <Typography color="text.secondary">{dateTime(d.server_time)} · {d.location ?? 'no location'}</Typography>
            <Alert severity={d.result === 'FLAGGED' ? 'warning' : d.result === 'REJECTED' ? 'error' : 'success'}>
              {REASONS[d.reason_code ?? ''] ?? d.reason_code ?? 'All checks passed'}
            </Alert>
            <Typography variant="subtitle2">Checks</Typography>
            <Stack spacing={0.5}>
              {Object.entries(d.checks).map(([key, value]) => (
                <Stack key={key} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
                  <Chip size="small" label={value === 'NOT_APPLICABLE' ? 'n/a' : value} color={SIGNAL_COLOR[value]} sx={{ width: 64 }} />
                  <Typography variant="body2" sx={{ flexGrow: 1 }}>{CHECKS[key] ?? key}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                    {d.details[key] ? Object.entries(d.details[key]).map(([k, v]) => `${k}=${v}`).join(' ') : ''}
                  </Typography>
                </Stack>
              ))}
            </Stack>
            <Divider />
            <Typography variant="body2">
              Position {d.latitude?.toFixed(5)}, {d.longitude?.toFixed(5)} · accuracy {d.accuracy_m} m ·
              reading {d.fix_age_ms != null ? `${Math.round(d.fix_age_ms / 1000)} s` : '—'} old<br />
              Phone: {d.device_model ?? '—'} ({d.device_status ?? '—'}) · app {d.app_version ?? '—'}<br />
              Risk score: {d.risk_score ?? '—'}
            </Typography>
            {d.latitude != null && (
              <Button size="small" href={`https://www.openstreetmap.org/?mlat=${d.latitude}&mlon=${d.longitude}#map=16/${d.latitude}/${d.longitude}`}
                target="_blank" rel="noreferrer">Open position on map</Button>
            )}
            {d.review_decision ? (
              <Alert severity={d.review_decision === 'APPROVED' ? 'success' : 'error'}>
                {d.review_decision === 'APPROVED' ? 'Approved' : 'Rejected'} by {d.reviewed_by}
                {d.review_note ? ` – "${d.review_note}"` : ''}
              </Alert>
            ) : d.result === 'FLAGGED' && (
              <>
                <Divider />
                {ownRecord ? <Alert severity="info">You can't review your own attendance.</Alert> : (
                  <>
                    <TextField label="Note (required when rejecting)" multiline minRows={2} value={note}
                      onChange={(e) => setNote(e.target.value)} />
                    {decide.error && <Alert severity="error">{decide.error instanceof ApiError ? decide.error.message : 'Failed'}</Alert>}
                    <Stack direction="row" spacing={2}>
                      <Button variant="contained" color="success" disabled={decide.isPending} onClick={() => decide.mutate('APPROVED')}>
                        Approve – counts as attendance
                      </Button>
                      <Button variant="outlined" color="error" disabled={decide.isPending || note.trim().length < 3}
                        onClick={() => decide.mutate('REJECTED')}>Reject</Button>
                    </Stack>
                  </>
                )}
              </>
            )}
          </Stack>
        )}
      </Box>
    </Drawer>
  )
}
