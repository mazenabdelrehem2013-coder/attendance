import DownloadIcon from '@mui/icons-material/Download'
import RefreshIcon from '@mui/icons-material/Refresh'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardActionArea from '@mui/material/CardActionArea'
import CardContent from '@mui/material/CardContent'
import IconButton from '@mui/material/IconButton'
import LinearProgress from '@mui/material/LinearProgress'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { apiDownload, apiGet, ApiError } from '../api/client'
import type { NamedItem, TeamAttendance, TeamSummary } from '../api/types'
import { useCurrentUser } from '../auth/AuthProvider'
import { DepartureChip, StatusChip, VerificationChip } from '../components/StatusChip'
import { formatMinutes, formatTime, longDate, todayIso } from '../lib/format'

/** Summary cards. Clicking one filters the table to those people. */
const CARDS: { key: keyof TeamSummary; label: string; filter: string; color: string }[] = [
  { key: 'total_employees', label: 'Employees', filter: '', color: 'text.primary' },
  { key: 'present', label: 'Present', filter: 'PRESENT_OR_LATE', color: 'success.main' },
  { key: 'late', label: 'Late', filter: 'LATE', color: 'warning.main' },
  { key: 'absent', label: 'Absent', filter: 'ABSENT', color: 'error.main' },
  { key: 'checked_in_now', label: 'Checked in now', filter: 'CHECKED_IN', color: 'success.main' },
  { key: 'missing_checkout', label: 'Missing check-out', filter: 'MISSING_CHECKOUT', color: 'error.main' },
  { key: 'suspicious', label: 'Suspicious', filter: 'SUSPICIOUS', color: 'secondary.main' },
  { key: 'on_leave', label: 'On leave', filter: 'ON_LEAVE', color: 'info.main' },
]

const STATUS_OPTIONS = [
  ['', 'All statuses'],
  ['PRESENT_OR_LATE', 'Present (incl. late)'],
  ['LATE', 'Late'],
  ['ABSENT', 'Absent'],
  ['NOT_CHECKED_IN', 'Not checked in yet'],
  ['CHECKED_IN', 'Checked in now'],
  ['MISSING_CHECKOUT', 'Missing check-out'],
  ['SUSPICIOUS', 'Pending review'],
  ['ON_LEAVE', 'On leave'],
]

function statusParam(filter: string): string[] | undefined {
  if (!filter) return undefined
  return filter === 'PRESENT_OR_LATE' ? ['PRESENT', 'LATE'] : [filter]
}

export function DashboardPage() {
  const user = useCurrentUser()
  const [date, setDate] = useState(todayIso())
  const [q, setQ] = useState('')
  const [department, setDepartment] = useState('')
  const [location, setLocation] = useState('')
  const [status, setStatus] = useState('')
  const [exportError, setExportError] = useState<string | null>(null)

  const params = {
    date,
    q: q.trim() || undefined,
    department_id: department || undefined,
    location_id: location || undefined,
    status: statusParam(status),
  }
  const isToday = date === todayIso()
  const team = useQuery({
    queryKey: ['team', params],
    queryFn: () => apiGet<TeamAttendance>('/manager/attendance', params),
    refetchInterval: isToday ? 60_000 : false, // today's view refreshes every minute
  })
  const departments = useQuery({ queryKey: ['departments'], queryFn: () => apiGet<NamedItem[]>('/departments') })
  const locations = useQuery({ queryKey: ['locations'], queryFn: () => apiGet<NamedItem[]>('/locations') })

  async function exportCsv() {
    setExportError(null)
    try {
      await apiDownload('/manager/attendance/export.csv', params, `attendance-${date}.csv`)
    } catch (e) {
      setExportError(e instanceof ApiError ? e.message : 'Export failed.')
    }
  }

  const scopeText = user.role === 'MANAGER' ? 'Your team' : 'All employees'
  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} useFlexGap sx={{ alignItems: 'center', flexWrap: 'wrap' }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>{scopeText}</Typography>
          <Typography color="text.secondary">{longDate(date)}</Typography>
        </Box>
        <TextField type="date" size="small" label="Date" value={date} onChange={(e) => e.target.value && setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }} />
        <Tooltip title="Refresh"><IconButton onClick={() => team.refetch()}><RefreshIcon /></IconButton></Tooltip>
        <Button variant="outlined" startIcon={<DownloadIcon />} onClick={exportCsv}>Export CSV</Button>
      </Stack>
      {exportError && <Alert severity="error">{exportError}</Alert>}

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}>
        {CARDS.map((c) => (
          <Card key={c.key} variant="outlined" sx={status === c.filter && c.filter ? { borderColor: c.color, borderWidth: 2 } : undefined}>
            <CardActionArea onClick={() => setStatus(status === c.filter ? '' : c.filter)}>
              <CardContent>
                <Typography variant="h4" sx={{ color: c.color, fontWeight: 700 }} data-testid={`card-${c.key}`}>
                  {team.data ? team.data.summary[c.key] : '–'}
                </Typography>
                <Typography color="text.secondary">{c.label}</Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </Box>

      <Paper variant="outlined">
        <Stack direction="row" spacing={2} useFlexGap sx={{ p: 2, flexWrap: 'wrap' }}>
          <TextField size="small" label="Search name or ID" value={q} onChange={(e) => setQ(e.target.value)} />
          <TextField select size="small" label="Department" value={department} onChange={(e) => setDepartment(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">All departments</MenuItem>
            {departments.data?.filter((d) => d.is_active).map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Location" value={location} onChange={(e) => setLocation(e.target.value)} sx={{ minWidth: 180 }}>
            <MenuItem value="">All locations</MenuItem>
            {locations.data?.map((l) => <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Status" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ minWidth: 200 }}>
            {STATUS_OPTIONS.map(([v, label]) => <MenuItem key={v} value={v}>{label}</MenuItem>)}
          </TextField>
        </Stack>
        {team.isFetching && <LinearProgress />}
        {team.error && <Alert severity="error" sx={{ m: 2 }}>{(team.error as Error).message}</Alert>}
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Employee</TableCell>
                <TableCell>Employee ID</TableCell>
                <TableCell>Department</TableCell>
                <TableCell>Location</TableCell>
                <TableCell>Check-in</TableCell>
                <TableCell>Check-out</TableCell>
                <TableCell>Working hours</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Verification</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {team.data?.rows.map((r) => (
                <TableRow key={r.employee_id} hover>
                  <TableCell>{r.full_name}</TableCell>
                  <TableCell>{r.employee_code}</TableCell>
                  <TableCell>{r.department ?? '—'}</TableCell>
                  <TableCell>{r.location ?? '—'}</TableCell>
                  <TableCell>{formatTime(r.check_in)}</TableCell>
                  <TableCell>{formatTime(r.check_out)}</TableCell>
                  <TableCell>{formatMinutes(r.worked_minutes)}</TableCell>
                  <TableCell><Stack direction="row" spacing={0.5}><StatusChip row={r} /><DepartureChip row={r} /></Stack></TableCell>
                  <TableCell><VerificationChip value={r.verification_status} /></TableCell>
                </TableRow>
              ))}
              {team.data && team.data.rows.length === 0 && (
                <TableRow><TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>No employees match these filters.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Stack>
  )
}
