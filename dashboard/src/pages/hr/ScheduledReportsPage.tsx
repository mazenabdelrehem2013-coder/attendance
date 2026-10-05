import AddIcon from '@mui/icons-material/Add'
import PlayArrowIcon from '@mui/icons-material/PlayArrow'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Checkbox from '@mui/material/Checkbox'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
import FormGroup from '@mui/material/FormGroup'
import FormLabel from '@mui/material/FormLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiDelete, apiGet, apiPost, apiPut } from '../../api/client'
import type { Department, Location } from '../../api/hrTypes'
import {
  DAY_NAMES, REPORT_LABELS, ROLE_LABELS,
  type AlertSetting, type RecipientRole, type Schedule, type ScheduleInput,
} from '../../api/scheduleTypes'
import { FormDialog } from '../../components/FormDialog'

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export function ScheduledReportsPage() {
  const [tab, setTab] = useState('schedules')
  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Scheduled reports & alerts</Typography>
      <Typography color="text.secondary">
        Reports created automatically at set times. They appear under <b>Reports → Ready reports</b> (dashboard and
        app) for HR and managers to download. Nothing is emailed.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="schedules" label="Scheduled reports" />
        <Tab value="alerts" label="Alerts" />
      </Tabs>
      {tab === 'schedules' ? <Schedules /> : <Alerts />}
    </Stack>
  )
}

// --- Scheduled reports ------------------------------------------------------------------------

const forWhom = (s: ScheduleInput) => s.recipient_roles.map((r) => ROLE_LABELS[r]).join(', ')

function Schedules() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Schedule | 'new' | null>(null)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const schedules = useQuery({ queryKey: ['report-schedules'], queryFn: () => apiGet<Schedule[]>('/hr/report-schedules') })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['report-schedules'] })

  async function runNow(s: Schedule) {
    try {
      const r = await apiPost<{ message: string }>(`/hr/report-schedules/${s.id}/run-now`)
      setMessage({ ok: true, text: `${s.name}: ${r.message}` })
      queryClient.invalidateQueries({ queryKey: ['ready-reports'] })
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : 'Could not create the report.' })
    }
  }

  async function remove(s: Schedule) {
    if (!confirm(`Delete the scheduled report "${s.name}"? Files already created stay available.`)) return
    await apiDelete(`/hr/report-schedules/${s.id}`)
    refresh()
  }

  return (
    <>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>New scheduled report</Button></Box>
      {message && <Alert severity={message.ok ? 'success' : 'error'} onClose={() => setMessage(null)}>{message.text}</Alert>}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Name</TableCell><TableCell>Report</TableCell><TableCell>When</TableCell><TableCell>For</TableCell>
            <TableCell>Next</TableCell><TableCell>Last created</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {schedules.data?.map((s) => (
              <TableRow key={s.id} hover>
                <TableCell>{s.name} {!s.is_enabled && <Chip size="small" label="Paused" sx={{ ml: 1 }} />}</TableCell>
                <TableCell>{REPORT_LABELS[s.report]} · {s.formats.map((f) => (f === 'EXCEL' ? 'Excel' : 'PDF')).join(' + ')}</TableCell>
                <TableCell>{s.description}</TableCell>
                <TableCell>{forWhom(s)}</TableCell>
                <TableCell>{when(s.next_run_at)}</TableCell>
                <TableCell>{when(s.last_run_at)}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  <Button size="small" startIcon={<PlayArrowIcon />} onClick={() => runNow(s)}>Create now</Button>
                  <Button size="small" onClick={() => setEditing(s)}>Edit</Button>
                  <Button size="small" color="error" onClick={() => remove(s)}>Delete</Button>
                </TableCell>
              </TableRow>
            ))}
            {schedules.data?.length === 0 && (
              <TableRow><TableCell colSpan={7}>
                <Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>
                  No scheduled reports yet. Example: the weekly report for HR and every manager, each Monday at 08:00.
                </Typography>
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
      {editing && <ScheduleDialog schedule={editing === 'new' ? null : editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    </>
  )
}

const NEW_SCHEDULE: ScheduleInput = {
  name: '', report: 'weekly', frequency: 'weekly', time: '08:00', days: [0, 1, 2, 3, 4, 5], weekday: 0, day_of_month: 1,
  daily_period: 'previous', formats: ['EXCEL', 'PDF'], recipient_roles: ['HR'],
  location_id: null, department_id: null, is_enabled: true,
}
const FIXED: Partial<Record<ScheduleInput['report'], ScheduleInput['frequency']>> = { daily: 'daily', weekly: 'weekly', monthly: 'monthly' }

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
}

function ScheduleDialog({ schedule, onClose, onSaved }: { schedule: Schedule | null; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState<ScheduleInput>(() => (schedule ? { ...schedule } : NEW_SCHEDULE))
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const departments = useQuery({ queryKey: ['departments'], queryFn: () => apiGet<Department[]>('/departments') })
  const set = (patch: Partial<ScheduleInput>) => setF((old) => ({ ...old, ...patch }))

  async function save() {
    const body: ScheduleInput = {
      name: f.name, report: f.report, frequency: f.frequency, time: f.time, days: f.days, weekday: f.weekday,
      day_of_month: f.day_of_month, daily_period: f.daily_period, formats: f.formats, recipient_roles: f.recipient_roles,
      location_id: f.location_id, department_id: f.department_id, is_enabled: f.is_enabled,
    }
    if (schedule) await apiPut(`/hr/report-schedules/${schedule.id}`, body)
    else await apiPost('/hr/report-schedules', body)
    onSaved()
  }

  return (
    <FormDialog open maxWidth="md" title={schedule ? 'Edit scheduled report' : 'New scheduled report'} onClose={onClose} onSubmit={save}>
      <TextField label="Name" required value={f.name} placeholder="e.g. Weekly report for managers"
        onChange={(e) => set({ name: e.target.value })} />
      <Stack direction="row" spacing={2}>
        <TextField select label="Report" value={f.report} sx={{ flex: 1 }}
          onChange={(e) => {
            const report = e.target.value as ScheduleInput['report']
            set({ report, frequency: FIXED[report] ?? f.frequency })
          }}>
          {Object.entries(REPORT_LABELS).map(([k, v]) => <MenuItem key={k} value={k}>{v}</MenuItem>)}
        </TextField>
        <TextField select label="How often" value={f.frequency} sx={{ flex: 1 }} disabled={Boolean(FIXED[f.report])}
          onChange={(e) => set({ frequency: e.target.value as ScheduleInput['frequency'] })}>
          <MenuItem value="daily">Daily</MenuItem><MenuItem value="weekly">Weekly</MenuItem><MenuItem value="monthly">Monthly</MenuItem>
        </TextField>
        <TextField type="time" label="Time" value={f.time} required sx={{ width: 140 }}
          slotProps={{ inputLabel: { shrink: true } }} onChange={(e) => set({ time: e.target.value })} />
      </Stack>

      {f.frequency === 'daily' && (
        <>
          <Box>
            <FormLabel>Create on</FormLabel>
            <Stack direction="row" spacing={1} sx={{ mt: 1 }}>
              {DAY_NAMES.map((d, i) => (
                <Chip key={d} label={d} color={f.days.includes(i) ? 'primary' : 'default'}
                  variant={f.days.includes(i) ? 'filled' : 'outlined'} onClick={() => set({ days: toggle(f.days, i).sort() })} />
              ))}
            </Stack>
          </Box>
          <TextField select label="Covers" value={f.daily_period}
            onChange={(e) => set({ daily_period: e.target.value as ScheduleInput['daily_period'] })}>
            <MenuItem value="previous">The previous working day (complete)</MenuItem>
            <MenuItem value="today">Today so far</MenuItem>
          </TextField>
        </>
      )}
      {f.frequency === 'weekly' && (
        <TextField select label="Day" value={f.weekday} helperText="Covers the previous week (Monday to Sunday)."
          onChange={(e) => set({ weekday: Number(e.target.value) })}>
          {DAY_NAMES.map((d, i) => <MenuItem key={d} value={i}>{d}</MenuItem>)}
        </TextField>
      )}
      {f.frequency === 'monthly' && (
        <TextField type="number" label="Day of the month" value={f.day_of_month}
          slotProps={{ htmlInput: { min: 1, max: 28 } }} helperText="1–28. Covers the previous month."
          onChange={(e) => set({ day_of_month: Number(e.target.value) })} />
      )}

      <Stack direction="row" spacing={4}>
        <Box>
          <FormLabel>Files</FormLabel>
          <FormGroup row>
            {(['EXCEL', 'PDF'] as const).map((fmt) => (
              <FormControlLabel key={fmt} label={fmt === 'EXCEL' ? 'Excel' : 'PDF'} control={
                <Checkbox checked={f.formats.includes(fmt)} onChange={() => set({ formats: toggle(f.formats, fmt) })} />} />
            ))}
          </FormGroup>
        </Box>
        <Box>
          <FormLabel>For</FormLabel>
          <FormGroup row>
            {(['HR', 'MANAGER', 'ADMIN'] as RecipientRole[]).map((r) => (
              <FormControlLabel key={r} label={r === 'MANAGER' ? 'Every manager (own team only)' : ROLE_LABELS[r]} control={
                <Checkbox checked={f.recipient_roles.includes(r)} onChange={() => set({ recipient_roles: toggle(f.recipient_roles, r) })} />} />
            ))}
          </FormGroup>
        </Box>
      </Stack>
      <Stack direction="row" spacing={2}>
        <TextField select label="Location" value={f.location_id ?? ''} sx={{ flex: 1 }}
          slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
          onChange={(e) => set({ location_id: e.target.value || null })}>
          <MenuItem value="">All locations</MenuItem>
          {locations.data?.map((l) => <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>)}
        </TextField>
        <TextField select label="Department" value={f.department_id ?? ''} sx={{ flex: 1 }}
          slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
          onChange={(e) => set({ department_id: e.target.value || null })}>
          <MenuItem value="">All departments</MenuItem>
          {departments.data?.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
        </TextField>
      </Stack>
      <FormControlLabel label="Active" control={<Switch checked={f.is_enabled} onChange={(e) => set({ is_enabled: e.target.checked })} />} />
    </FormDialog>
  )
}

// --- Alerts -----------------------------------------------------------------------------------

function Alerts() {
  const queryClient = useQueryClient()
  const settings = useQuery({ queryKey: ['alert-settings'], queryFn: () => apiGet<AlertSetting[]>('/hr/alert-settings') })
  const [error, setError] = useState<string | null>(null)

  async function save(a: AlertSetting) {
    setError(null)
    try {
      await apiPut(`/hr/alert-settings/${a.event}`, { enabled: a.enabled, roles: a.roles, thresholds: a.thresholds })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Saving failed.')
    }
    queryClient.invalidateQueries({ queryKey: ['alert-settings'] })
  }

  return (
    <>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
      <Typography color="text.secondary">
        Alerts appear under the bell icon in the dashboard. “Manager” means the employee’s own manager. Changes are saved straight away.
      </Typography>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Alert</TableCell><TableCell>On</TableCell><TableCell>Who sees it</TableCell></TableRow></TableHead>
          <TableBody>
            {settings.data?.map((a) => (
              <TableRow key={a.event}>
                <TableCell sx={{ maxWidth: 420 }}>
                  <Typography sx={{ fontWeight: 600 }}>{a.label}</Typography>
                  <Typography variant="body2" color="text.secondary">{a.description}</Typography>
                  {a.event === 'HIGH_ABSENCE' && (
                    <Stack direction="row" spacing={1} sx={{ mt: 1, alignItems: 'center' }}>
                      <TextField size="small" type="number" label="Absences" sx={{ width: 100 }}
                        defaultValue={a.thresholds.absences} slotProps={{ htmlInput: { min: 1, max: 31 } }}
                        onBlur={(e) => save({ ...a, thresholds: { ...a.thresholds, absences: Number(e.target.value) } })} />
                      <Typography variant="body2">in</Typography>
                      <TextField size="small" type="number" label="Days" sx={{ width: 90 }}
                        defaultValue={a.thresholds.days} slotProps={{ htmlInput: { min: 7, max: 92 } }}
                        onBlur={(e) => save({ ...a, thresholds: { ...a.thresholds, days: Number(e.target.value) } })} />
                    </Stack>
                  )}
                </TableCell>
                <TableCell>
                  <Switch checked={a.enabled} slotProps={{ input: { 'aria-label': `${a.label} on` } }}
                    onChange={(e) => save({ ...a, enabled: e.target.checked })} />
                </TableCell>
                <TableCell>
                  <Stack direction="row" spacing={0.5} sx={{ flexWrap: 'wrap' }}>
                    {(['MANAGER', 'HR', 'ADMIN'] as RecipientRole[]).map((r) => (
                      <Chip key={r} size="small" label={r === 'MANAGER' ? 'Manager' : ROLE_LABELS[r]} disabled={!a.enabled}
                        color={a.roles.includes(r) ? 'primary' : 'default'} variant={a.roles.includes(r) ? 'filled' : 'outlined'}
                        onClick={() => save({ ...a, roles: toggle(a.roles, r) })} />
                    ))}
                  </Stack>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </>
  )
}
