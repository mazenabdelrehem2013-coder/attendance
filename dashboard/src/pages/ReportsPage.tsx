import DownloadIcon from '@mui/icons-material/Download'
import PictureAsPdfIcon from '@mui/icons-material/PictureAsPdf'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import LinearProgress from '@mui/material/LinearProgress'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableContainer from '@mui/material/TableContainer'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { apiDownloadPost, apiGet, ApiError } from '../api/client'
import type { Department, Location, ManagerOption } from '../api/hrTypes'
import { useCurrentUser } from '../auth/AuthProvider'
import { ReadyReports } from '../components/ReadyReports'
import { formatMinutes, todayIso } from '../lib/format'

type ReportType = 'daily' | 'weekly' | 'monthly' | 'period' | 'late' | 'absence' | 'suspicious'

const TYPES: { value: ReportType; label: string }[] = [
  { value: 'daily', label: 'Daily report' },
  { value: 'weekly', label: 'Weekly report' },
  { value: 'monthly', label: 'Monthly report' },
  { value: 'period', label: 'Custom period (employee / location / department / manager)' },
  { value: 'late', label: 'Late arrivals' },
  { value: 'absence', label: 'Absences' },
  { value: 'suspicious', label: 'Suspicious attendance' },
]

interface DailyReport { title: string; rows: Record<string, string | number | null>[]; totals: Record<string, number> }
interface PeriodRow {
  employee_id: string; employee: string; employee_code: string; department: string | null; manager: string | null
  location: string | null; working_days: number; present_days: number; late_days: number; absent_days: number
  leave_days: number; early_departure_days: number; missing_checkout_days: number; average_check_in: string | null
  average_check_out: string | null; average_worked_minutes: number | null; attendance_rate: number | null
}
interface Group { name: string; employees: number; working_days: number; present_days: number; late_days: number; absent_days: number; attendance_rate: number | null }
interface PeriodReport { title: string; date_from: string; date_to: string; rows: PeriodRow[]; totals: Record<string, number | null>; by_location: Group[]; by_department: Group[]; by_manager: Group[] }
interface ListReport { title: string; rows: { date: string; employee: string; employee_code: string; department: string | null; location: string | null; detail: string }[] }

const pct = (v: number | null) => (v == null ? '—' : `${Math.round(v * 1000) / 10}%`)
const firstOfMonth = (iso: string) => `${iso.slice(0, 8)}01`

export function ReportsPage() {
  const user = useCurrentUser()
  const isHr = user.role === 'HR' || user.role === 'ADMIN'
  const today = todayIso()
  const [type, setType] = useState<ReportType>('daily')
  const [searchParams] = useSearchParams()
  const [tab, setTab] = useState<'create' | 'ready'>(searchParams.get('tab') === 'ready' ? 'ready' : 'create')
  const [date, setDate] = useState(today)
  const [month, setMonth] = useState(today.slice(0, 7))
  const [from, setFrom] = useState(firstOfMonth(today))
  const [to, setTo] = useState(today)
  const [department, setDepartment] = useState('')
  const [location, setLocation] = useState('')
  const [manager, setManager] = useState('')

  const departments = useQuery({ queryKey: ['departments'], queryFn: () => apiGet<Department[]>('/departments') })
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const managers = useQuery({ queryKey: ['managers'], queryFn: () => apiGet<ManagerOption[]>('/managers'), enabled: isHr })

  const params: Record<string, string | undefined> = {
    department_id: department || undefined, location_id: location || undefined, manager_id: manager || undefined,
    ...(type === 'daily' || type === 'weekly' ? { date } : type === 'monthly' ? { month } : { from, to }),
  }
  const report = useQuery({
    queryKey: ['report', type, params],
    queryFn: () => apiGet<DailyReport | PeriodReport | ListReport>(`/reports/${type}`, params),
  })
  const [downloading, setDownloading] = useState<'excel' | 'pdf' | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function download(format: 'excel' | 'pdf') {
    setDownloading(format)
    setDownloadError(null)
    try {
      await apiDownloadPost(`/reports/export/${format}`, {
        report: type,
        date: type === 'daily' || type === 'weekly' ? date : undefined,
        month: type === 'monthly' ? month : undefined,
        date_from: ['period', 'late', 'absence', 'suspicious'].includes(type) ? from : undefined,
        date_to: ['period', 'late', 'absence', 'suspicious'].includes(type) ? to : undefined,
        department_id: department || undefined,
        location_id: location || undefined,
        manager_id: manager || undefined,
      })
    } catch (e) {
      setDownloadError(e instanceof ApiError ? e.message : 'Download failed.')
    } finally {
      setDownloading(null)
    }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Reports</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="create" label="Create a report" />
        <Tab value="ready" label="Ready reports" />
      </Tabs>
      {tab === 'ready' ? <ReadyReports /> : <>
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap' }}>
          <TextField select size="small" label="Report" value={type} onChange={(e) => setType(e.target.value as ReportType)} sx={{ minWidth: 300 }}>
            {TYPES.map((t) => <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>)}
          </TextField>
          {(type === 'daily' || type === 'weekly') && (
            <TextField type="date" size="small" label={type === 'weekly' ? 'Any day in the week' : 'Date'} value={date}
              onChange={(e) => e.target.value && setDate(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          )}
          {type === 'monthly' && (
            <TextField type="month" size="small" label="Month" value={month}
              onChange={(e) => e.target.value && setMonth(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
          )}
          {!['daily', 'weekly', 'monthly'].includes(type) && (
            <>
              <TextField type="date" size="small" label="From" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
              <TextField type="date" size="small" label="To" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} slotProps={{ inputLabel: { shrink: true } }} />
            </>
          )}
          <TextField select size="small" label="Location" value={location} onChange={(e) => setLocation(e.target.value)} sx={{ minWidth: 170 }}>
            <MenuItem value="">All locations</MenuItem>
            {locations.data?.map((l) => <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Department" value={department} onChange={(e) => setDepartment(e.target.value)} sx={{ minWidth: 170 }}>
            <MenuItem value="">All departments</MenuItem>
            {departments.data?.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
          </TextField>
          {isHr && (
            <TextField select size="small" label="Manager" value={manager} onChange={(e) => setManager(e.target.value)} sx={{ minWidth: 170 }}>
              <MenuItem value="">All managers</MenuItem>
              {managers.data?.map((m) => <MenuItem key={m.id} value={m.id}>{m.name}</MenuItem>)}
            </TextField>
          )}
        </Stack>
        <Stack direction="row" spacing={2} sx={{ mt: 2, alignItems: 'center' }}>
          <Button variant="contained" startIcon={<DownloadIcon />} disabled={!!downloading} onClick={() => download('excel')}>
            {downloading === 'excel' ? 'Preparing…' : 'Download Excel'}
          </Button>
          <Button variant="outlined" startIcon={<PictureAsPdfIcon />} disabled={!!downloading} onClick={() => download('pdf')}>
            {downloading === 'pdf' ? 'Preparing…' : 'Download PDF'}
          </Button>
          <Typography variant="caption" color="text.secondary">
            {user.role === 'MANAGER' ? 'Reports contain only your own team. ' : ''}Downloads are recorded in the audit log.
          </Typography>
        </Stack>
        {downloadError && <Alert severity="error" sx={{ mt: 2 }}>{downloadError}</Alert>}
      </Paper>
      {report.isFetching && <LinearProgress />}
      {report.error && <Alert severity="error">{(report.error as Error).message}</Alert>}
      {report.data && (type === 'daily' ? <Daily data={report.data as DailyReport} />
        : ['weekly', 'monthly', 'period'].includes(type) ? <Period data={report.data as PeriodReport} />
          : <List data={report.data as ListReport} />)}
      </>}
    </Stack>
  )
}

function Totals({ items }: { items: [string, string | number][] }) {
  return (
    <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
      {items.map(([label, value]) => (
        <Paper key={label} variant="outlined" sx={{ p: 1.5 }}>
          <Typography variant="h6" sx={{ fontWeight: 700 }}>{value}</Typography>
          <Typography variant="body2" color="text.secondary">{label}</Typography>
        </Paper>
      ))}
    </Box>
  )
}

function Daily({ data }: { data: DailyReport }) {
  const t = data.totals
  return (
    <>
      <Totals items={[['Employees', t.employees], ['Present', t.present], ['Late', t.late], ['Absent', t.absent],
        ['Missing check-out', t.missing_checkout], ['Pending review', t.pending_review], ['On leave', t.on_leave]]} />
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            {['Employee', 'Employee ID', 'Department', 'Manager', 'Location', 'Check-in', 'Check-out', 'Working hours', 'Status', 'Verification'].map((h) => <TableCell key={h}>{h}</TableCell>)}
          </TableRow></TableHead>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={String(r.employee_code)}>
                <TableCell>{r.employee}</TableCell><TableCell>{r.employee_code}</TableCell><TableCell>{r.department ?? '—'}</TableCell>
                <TableCell>{r.manager ?? '—'}</TableCell><TableCell>{r.location ?? '—'}</TableCell>
                <TableCell>{r.check_in ?? '—'}</TableCell><TableCell>{r.check_out ?? '—'}</TableCell>
                <TableCell>{formatMinutes(Number(r.worked_minutes))}</TableCell>
                <TableCell>{String(r.status).replaceAll('_', ' ').toLowerCase()}</TableCell>
                <TableCell>{r.verification_status ? String(r.verification_status).replaceAll('_', ' ').toLowerCase() : '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </>
  )
}

function Period({ data }: { data: PeriodReport }) {
  const t = data.totals
  return (
    <>
      <Typography color="text.secondary">{data.title}: {data.date_from} to {data.date_to}</Typography>
      <Totals items={[['Employees', t.employees ?? 0], ['Working days', t.working_days ?? 0], ['Present days', t.present_days ?? 0],
        ['Late days', t.late_days ?? 0], ['Absent days', t.absent_days ?? 0], ['Attendance', pct(t.attendance_rate as number | null)]]} />
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            {['Employee', 'ID', 'Department', 'Working days', 'Present', 'Absent', 'Late', 'Left early', 'Missing check-out', 'Leave',
              'Avg check-in', 'Avg check-out', 'Avg hours', 'Attendance'].map((h) => <TableCell key={h}>{h}</TableCell>)}
          </TableRow></TableHead>
          <TableBody>
            {data.rows.map((r) => (
              <TableRow key={r.employee_id}>
                <TableCell>{r.employee}</TableCell><TableCell>{r.employee_code}</TableCell><TableCell>{r.department ?? '—'}</TableCell>
                <TableCell>{r.working_days}</TableCell><TableCell>{r.present_days}</TableCell><TableCell>{r.absent_days}</TableCell>
                <TableCell>{r.late_days}</TableCell><TableCell>{r.early_departure_days}</TableCell><TableCell>{r.missing_checkout_days}</TableCell>
                <TableCell>{r.leave_days}</TableCell><TableCell>{r.average_check_in ?? '—'}</TableCell><TableCell>{r.average_check_out ?? '—'}</TableCell>
                <TableCell>{r.average_worked_minutes ? formatMinutes(r.average_worked_minutes) : '—'}</TableCell>
                <TableCell>{pct(r.attendance_rate)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr 1fr' } }}>
        <GroupTable title="By location" groups={data.by_location} />
        <GroupTable title="By department" groups={data.by_department} />
        <GroupTable title="By manager" groups={data.by_manager} />
      </Box>
    </>
  )
}

function GroupTable({ title, groups }: { title: string; groups: Group[] }) {
  return (
    <Paper variant="outlined">
      <Typography sx={{ fontWeight: 600, p: 1.5 }}>{title}</Typography>
      <Table size="small">
        <TableHead><TableRow><TableCell>Name</TableCell><TableCell>People</TableCell><TableCell>Absent days</TableCell><TableCell>Attendance</TableCell></TableRow></TableHead>
        <TableBody>
          {groups.map((g) => (
            <TableRow key={g.name}><TableCell>{g.name}</TableCell><TableCell>{g.employees}</TableCell><TableCell>{g.absent_days}</TableCell><TableCell>{pct(g.attendance_rate)}</TableCell></TableRow>
          ))}
        </TableBody>
      </Table>
    </Paper>
  )
}

function List({ data }: { data: ListReport }) {
  return (
    <TableContainer component={Paper} variant="outlined">
      <Table size="small">
        <TableHead><TableRow>{['Date', 'Employee', 'ID', 'Department', 'Location', 'Details'].map((h) => <TableCell key={h}>{h}</TableCell>)}</TableRow></TableHead>
        <TableBody>
          {data.rows.map((r, i) => (
            <TableRow key={i}>
              <TableCell>{r.date}</TableCell><TableCell>{r.employee}</TableCell><TableCell>{r.employee_code}</TableCell>
              <TableCell>{r.department ?? '—'}</TableCell><TableCell>{r.location ?? '—'}</TableCell><TableCell>{r.detail}</TableCell>
            </TableRow>
          ))}
          {data.rows.length === 0 && <TableRow><TableCell colSpan={6} align="center" sx={{ py: 4, color: 'text.secondary' }}>Nothing in this period.</TableCell></TableRow>}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
