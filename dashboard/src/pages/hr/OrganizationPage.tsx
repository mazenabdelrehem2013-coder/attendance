import AddIcon from '@mui/icons-material/Add'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
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

import { apiGet, apiPost, apiPut } from '../../api/client'
import type { Branch, Department, Location, Schedule, ScheduleDay } from '../../api/hrTypes'
import { useCurrentUser } from '../../auth/AuthProvider'
import { FormDialog } from '../../components/FormDialog'

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

function ActiveChip({ active }: { active: boolean }) {
  return <Chip size="small" label={active ? 'Active' : 'Disabled'} color={active ? 'success' : 'default'} />
}

export function OrganizationPage() {
  const [tab, setTab] = useState('locations')
  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Organization</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="locations" label="Locations" />
        <Tab value="departments" label="Departments" />
        <Tab value="schedules" label="Working hours" />
        <Tab value="branches" label="Branches" />
      </Tabs>
      {tab === 'locations' && <Locations />}
      {tab === 'departments' && <Departments />}
      {tab === 'schedules' && <Schedules />}
      {tab === 'branches' && <Branches />}
    </Stack>
  )
}

// --- Locations ------------------------------------------------------------------------------

function Locations() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Location | 'new' | null>(null)
  const locations = useQuery({ queryKey: ['locations-all', 'inactive'], queryFn: () => apiGet<Location[]>('/locations', { include_inactive: 'true' }) })
  const schedules = useQuery({ queryKey: ['schedules'], queryFn: () => apiGet<Schedule[]>('/work-schedules') })
  const scheduleName = (id: string | null) => schedules.data?.find((s) => s.id === id)?.name ?? '—'

  return (
    <>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>Add location</Button></Box>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Name</TableCell><TableCell>Code</TableCell><TableCell>Address</TableCell><TableCell>Coordinates</TableCell>
            <TableCell>Radius</TableCell><TableCell>Working hours</TableCell><TableCell>Status</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {locations.data?.map((l) => (
              <TableRow key={l.id} hover>
                <TableCell>{l.name}</TableCell><TableCell>{l.code}</TableCell><TableCell>{l.address ?? '—'}</TableCell>
                <TableCell sx={{ fontFamily: 'monospace' }}>{l.latitude}, {l.longitude}</TableCell>
                <TableCell>{l.radius_m} m</TableCell>
                <TableCell>{scheduleName(l.work_schedule_id)}</TableCell>
                <TableCell><ActiveChip active={l.is_active} /></TableCell>
                <TableCell><Button size="small" onClick={() => setEditing(l)}>Edit</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editing && <LocationDialog location={editing === 'new' ? null : editing} schedules={schedules.data ?? []}
        onClose={() => setEditing(null)} onSaved={() => queryClient.invalidateQueries({ queryKey: ['locations-all'] })} />}
    </>
  )
}

function LocationDialog({ location, schedules, onClose, onSaved }: {
  location: Location | null; schedules: Schedule[]; onClose: () => void; onSaved: () => void
}) {
  const branches = useQuery({ queryKey: ['branches'], queryFn: () => apiGet<Branch[]>('/branches') })
  const [f, setF] = useState({
    name: location?.name ?? '', code: location?.code ?? '', address: location?.address ?? '',
    branch_id: location?.branch_id ?? '', latitude: location?.latitude ?? '', longitude: location?.longitude ?? '',
    radius_m: String(location?.radius_m ?? 200), timezone: location?.timezone ?? 'Africa/Lagos',
    work_schedule_id: location?.work_schedule_id ?? '', is_active: location?.is_active ?? true,
  })
  const set = (k: keyof typeof f) => (e: { target: { value: string } }) => setF({ ...f, [k]: e.target.value })
  // Google Maps copies "lat, lng" as one text: pasted into either box, it fills both.
  const setCoordinate = (k: 'latitude' | 'longitude') => (e: { target: { value: string } }) => {
    const pair = e.target.value.match(/^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$/)
    if (pair) setF({ ...f, latitude: pair[1], longitude: pair[2] })
    else setF({ ...f, [k]: e.target.value })
  }

  async function save() {
    const body = {
      name: f.name, code: f.code, address: f.address || null, branch_id: f.branch_id,
      latitude: Number(f.latitude), longitude: Number(f.longitude), radius_m: Number(f.radius_m),
      timezone: f.timezone, work_schedule_id: f.work_schedule_id || null,
    }
    if (location) await apiPut(`/locations/${location.id}`, { ...body, is_active: f.is_active })
    else await apiPost('/locations', body)
    onSaved()
  }

  return (
    <FormDialog open title={location ? `Edit ${location.name}` : 'Add location'} onClose={onClose} onSubmit={save}>
      <TextField label="Name" required value={f.name} onChange={set('name')} />
      <TextField label="Code" required value={f.code} onChange={set('code')} helperText="Short code, e.g. LOS" />
      <TextField select label="Branch" required value={f.branch_id} onChange={set('branch_id')}>
        {branches.data?.map((b) => <MenuItem key={b.id} value={b.id}>{b.name}</MenuItem>)}
      </TextField>
      <TextField label="Address" value={f.address} onChange={set('address')} />
      <Stack direction="row" spacing={2}>
        <TextField label="Latitude" required value={f.latitude} onChange={setCoordinate('latitude')} helperText="e.g. 6.428100" fullWidth />
        <TextField label="Longitude" required value={f.longitude} onChange={setCoordinate('longitude')} helperText="e.g. 3.421900" fullWidth />
      </Stack>
      <Typography variant="caption" color="text.secondary">
        Tip: in Google Maps, right-click the office entrance and click the numbers at the top to copy them.
      </Typography>
      <TextField label="Allowed radius (meters)" type="number" required value={f.radius_m} onChange={set('radius_m')}
        helperText="Between 10 and 5000. 100–200 m suits most offices." />
      <TextField label="Timezone" required value={f.timezone} onChange={set('timezone')} helperText="e.g. Africa/Lagos" />
      <TextField select label="Working hours" value={f.work_schedule_id} onChange={set('work_schedule_id')}>
        <MenuItem value="">—</MenuItem>
        {schedules.map((s) => <MenuItem key={s.id} value={s.id}>{s.name}</MenuItem>)}
      </TextField>
      {location && <FormControlLabel label="Active (people can check in here)" control={
        <Switch checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />} />}
    </FormDialog>
  )
}

// --- Departments ----------------------------------------------------------------------------

function Departments() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Department | 'new' | null>(null)
  const departments = useQuery({ queryKey: ['departments'], queryFn: () => apiGet<Department[]>('/departments') })
  return (
    <>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>Add department</Button></Box>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Code</TableCell><TableCell>Status</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {departments.data?.map((d) => (
              <TableRow key={d.id} hover>
                <TableCell>{d.name}</TableCell><TableCell>{d.code}</TableCell><TableCell><ActiveChip active={d.is_active} /></TableCell>
                <TableCell><Button size="small" onClick={() => setEditing(d)}>Edit</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editing && <SimpleDialog kind="Department" path="/departments" item={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => queryClient.invalidateQueries({ queryKey: ['departments'] })} />}
    </>
  )
}

function SimpleDialog({ kind, path, item, onClose, onSaved }: {
  kind: string; path: string; item: { id: string; name: string; code: string; is_active: boolean } | null
  onClose: () => void; onSaved: () => void
}) {
  const [f, setF] = useState({ name: item?.name ?? '', code: item?.code ?? '', is_active: item?.is_active ?? true })
  return (
    <FormDialog open title={item ? `Edit ${item.name}` : `Add ${kind.toLowerCase()}`} onClose={onClose}
      onSubmit={async () => {
        if (item) await apiPut(`${path}/${item.id}`, f)
        else await apiPost(path, { name: f.name, code: f.code })
        onSaved()
      }}>
      <TextField label="Name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <TextField label="Code" required value={f.code} onChange={(e) => setF({ ...f, code: e.target.value })} />
      {item && <FormControlLabel label="Active" control={
        <Switch checked={f.is_active} onChange={(e) => setF({ ...f, is_active: e.target.checked })} />} />}
    </FormDialog>
  )
}

// --- Branches (admin only can change) -------------------------------------------------------

function Branches() {
  const me = useCurrentUser()
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Branch | 'new' | null>(null)
  const branches = useQuery({ queryKey: ['branches'], queryFn: () => apiGet<Branch[]>('/branches') })
  const isAdmin = me.role === 'ADMIN'
  return (
    <>
      {isAdmin ? <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>Add branch</Button></Box>
        : <Typography color="text.secondary">Only administrators can change branches.</Typography>}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Code</TableCell><TableCell>Status</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {branches.data?.map((b) => (
              <TableRow key={b.id} hover>
                <TableCell>{b.name}</TableCell><TableCell>{b.code}</TableCell><TableCell><ActiveChip active={b.is_active} /></TableCell>
                <TableCell>{isAdmin && <Button size="small" onClick={() => setEditing(b)}>Edit</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editing && <SimpleDialog kind="Branch" path="/branches" item={editing === 'new' ? null : editing}
        onClose={() => setEditing(null)} onSaved={() => queryClient.invalidateQueries({ queryKey: ['branches'] })} />}
    </>
  )
}

// --- Working hours --------------------------------------------------------------------------

function Schedules() {
  const queryClient = useQueryClient()
  const [editing, setEditing] = useState<Schedule | 'new' | null>(null)
  const schedules = useQuery({ queryKey: ['schedules'], queryFn: () => apiGet<Schedule[]>('/work-schedules') })
  const hhmm = (t: string) => t.slice(0, 5)
  return (
    <>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>Add working hours</Button></Box>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Name</TableCell><TableCell>Days</TableCell><TableCell>Grace</TableCell><TableCell>Early leave allowed</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {schedules.data?.map((s) => (
              <TableRow key={s.id} hover>
                <TableCell>{s.name}</TableCell>
                <TableCell>{s.days.map((d) => `${WEEKDAYS[d.weekday].slice(0, 3)} ${hhmm(d.start_time)}–${hhmm(d.end_time)}`).join(', ')}</TableCell>
                <TableCell>{s.grace_minutes} min</TableCell>
                <TableCell>{s.early_departure_minutes} min</TableCell>
                <TableCell><Button size="small" onClick={() => setEditing(s)}>Edit</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editing && <ScheduleDialog schedule={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ['schedules'] })} />}
    </>
  )
}

function ScheduleDialog({ schedule, onClose, onSaved }: { schedule: Schedule | null; onClose: () => void; onSaved: () => void }) {
  const [name, setName] = useState(schedule?.name ?? '')
  const [grace, setGrace] = useState(String(schedule?.grace_minutes ?? 15))
  const [early, setEarly] = useState(String(schedule?.early_departure_minutes ?? 0))
  const [days, setDays] = useState<Record<number, ScheduleDay | null>>(() => {
    const init: Record<number, ScheduleDay | null> = {}
    WEEKDAYS.forEach((_, i) => {
      const d = schedule?.days.find((x) => x.weekday === i)
      init[i] = d ? { weekday: i, start_time: d.start_time.slice(0, 5), end_time: d.end_time.slice(0, 5) }
        : schedule ? null : i < 6 ? { weekday: i, start_time: '09:00', end_time: '18:00' } : null
    })
    return init
  })

  async function save() {
    const body = {
      name, grace_minutes: Number(grace), early_departure_minutes: Number(early),
      days: Object.values(days).filter((d): d is ScheduleDay => !!d),
    }
    if (schedule) await apiPut(`/work-schedules/${schedule.id}`, body)
    else await apiPost('/work-schedules', body)
    onSaved()
  }

  return (
    <FormDialog open title={schedule ? `Edit ${schedule.name}` : 'Add working hours'} onClose={onClose} onSubmit={save}>
      <TextField label="Name" required value={name} onChange={(e) => setName(e.target.value)} />
      {WEEKDAYS.map((label, i) => (
        <Stack key={label} direction="row" spacing={2} sx={{ alignItems: 'center' }}>
          <FormControlLabel sx={{ width: 150 }} label={label} control={
            <Switch checked={!!days[i]} onChange={(e) => setDays({ ...days, [i]: e.target.checked ? { weekday: i, start_time: '09:00', end_time: '18:00' } : null })} />} />
          {days[i] && (
            <>
              <TextField type="time" size="small" label="Start" value={days[i]!.start_time}
                onChange={(e) => setDays({ ...days, [i]: { ...days[i]!, start_time: e.target.value } })} />
              <TextField type="time" size="small" label="End" value={days[i]!.end_time}
                onChange={(e) => setDays({ ...days, [i]: { ...days[i]!, end_time: e.target.value } })} />
            </>
          )}
        </Stack>
      ))}
      <TextField label="Grace period (minutes)" type="number" value={grace} onChange={(e) => setGrace(e.target.value)}
        helperText="Arriving within this time after the start still counts as present." />
      <TextField label="Early leave allowed (minutes)" type="number" value={early} onChange={(e) => setEarly(e.target.value)}
        helperText="Leaving this many minutes before the end is not an early departure." />
    </FormDialog>
  )
}
