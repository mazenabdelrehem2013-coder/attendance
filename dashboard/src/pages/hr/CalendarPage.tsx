import AddIcon from '@mui/icons-material/Add'
import Autocomplete from '@mui/material/Autocomplete'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import MenuItem from '@mui/material/MenuItem'
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
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { apiDelete, apiGet, apiPost } from '../../api/client'
import type { Employee, Holiday, Leave, Location, Page } from '../../api/hrTypes'
import { FormDialog } from '../../components/FormDialog'

const LEAVE_TYPES = ['ANNUAL', 'SICK', 'MATERNITY', 'PATERNITY', 'OFFICIAL_DUTY', 'UNPAID', 'OTHER']
const label = (t: string) => t.toLowerCase().replace('_', ' ')

export function CalendarPage() {
  const [tab, setTab] = useState('holidays')
  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Holidays & leave</Typography>
      <Typography color="text.secondary">
        People on leave or on a holiday are not counted as absent. Moving holidays (Easter, Eid…) must be added each year.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="holidays" label="Holidays" />
        <Tab value="leave" label="Leave" />
      </Tabs>
      {tab === 'holidays' ? <Holidays /> : <LeaveList />}
    </Stack>
  )
}

function Holidays() {
  const queryClient = useQueryClient()
  const [year, setYear] = useState(new Date().getFullYear())
  const [adding, setAdding] = useState(false)
  const holidays = useQuery({ queryKey: ['holidays', year], queryFn: () => apiGet<Holiday[]>('/holidays', { year: String(year) }) })
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const locName = (id: string | null) => (id ? locations.data?.find((l) => l.id === id)?.name ?? '—' : 'All locations')

  async function remove(h: Holiday) {
    if (!confirm(`Remove "${h.name}"?`)) return
    await apiDelete(`/holidays/${h.id}`)
    queryClient.invalidateQueries({ queryKey: ['holidays'] })
  }

  return (
    <>
      <Stack direction="row" spacing={2}>
        <TextField select size="small" label="Year" value={year} onChange={(e) => setYear(Number(e.target.value))}>
          {[year - 1, year, year + 1].map((y) => <MenuItem key={y} value={y}>{y}</MenuItem>)}
        </TextField>
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>Add holiday</Button>
      </Stack>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Date</TableCell><TableCell>Name</TableCell><TableCell>Where</TableCell><TableCell /></TableRow></TableHead>
          <TableBody>
            {holidays.data?.map((h) => (
              <TableRow key={h.id} hover>
                <TableCell>{h.holiday_date}</TableCell><TableCell>{h.name}</TableCell><TableCell>{locName(h.location_id)}</TableCell>
                <TableCell><Button size="small" color="error" onClick={() => remove(h)}>Remove</Button></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {adding && <HolidayDialog locations={locations.data ?? []} onClose={() => setAdding(false)}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ['holidays'] })} />}
    </>
  )
}

function HolidayDialog({ locations, onClose, onSaved }: { locations: Location[]; onClose: () => void; onSaved: () => void }) {
  const [f, setF] = useState({ holiday_date: '', name: '', location_id: '' })
  return (
    <FormDialog open title="Add holiday" onClose={onClose}
      onSubmit={async () => { await apiPost('/holidays', { ...f, location_id: f.location_id || null }); onSaved() }}>
      <TextField type="date" label="Date" required value={f.holiday_date} slotProps={{ inputLabel: { shrink: true } }}
        onChange={(e) => setF({ ...f, holiday_date: e.target.value })} />
      <TextField label="Name" required value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
      <TextField select label="Where" value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}>
        <MenuItem value="">All locations</MenuItem>
        {locations.map((l) => <MenuItem key={l.id} value={l.id}>{l.name} only</MenuItem>)}
      </TextField>
    </FormDialog>
  )
}

function LeaveList() {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const leave = useQuery({ queryKey: ['leave'], queryFn: () => apiGet<Leave[]>('/leave') })

  async function cancel(l: Leave) {
    if (!confirm(`Cancel ${l.employee_name}'s leave?`)) return
    await apiPost(`/leave/${l.id}/cancel`)
    queryClient.invalidateQueries({ queryKey: ['leave'] })
  }

  return (
    <>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>Record leave</Button></Box>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Employee</TableCell><TableCell>Type</TableCell><TableCell>From</TableCell><TableCell>To</TableCell>
            <TableCell>Note</TableCell><TableCell>Status</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {leave.data?.map((l) => (
              <TableRow key={l.id} hover>
                <TableCell>{l.employee_name}</TableCell><TableCell>{label(l.leave_type)}</TableCell>
                <TableCell>{l.start_date}</TableCell><TableCell>{l.end_date}</TableCell><TableCell>{l.note ?? ''}</TableCell>
                <TableCell><Chip size="small" label={l.status.toLowerCase()} color={l.status === 'APPROVED' ? 'success' : 'default'} /></TableCell>
                <TableCell>{l.status === 'APPROVED' && <Button size="small" color="error" onClick={() => cancel(l)}>Cancel</Button>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {adding && <LeaveDialog onClose={() => setAdding(false)} onSaved={() => queryClient.invalidateQueries({ queryKey: ['leave'] })} />}
    </>
  )
}

function LeaveDialog({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const employees = useQuery({ queryKey: ['employees', ''], queryFn: () => apiGet<Page<Employee>>('/employees', { page_size: '200' }) })
  const [f, setF] = useState({ employee_id: '', leave_type: 'ANNUAL', start_date: '', end_date: '', note: '' })
  return (
    <FormDialog open title="Record leave" onClose={onClose}
      onSubmit={async () => { await apiPost('/leave', { ...f, note: f.note || null }); onSaved() }}>
      <Autocomplete options={employees.data?.items ?? []} getOptionLabel={(e) => `${e.full_name} (${e.employee_code})`}
        onChange={(_, e) => setF({ ...f, employee_id: e?.id ?? '' })}
        renderInput={(p) => <TextField {...p} label="Employee" required />} />
      <TextField select label="Type" value={f.leave_type} onChange={(e) => setF({ ...f, leave_type: e.target.value })}>
        {LEAVE_TYPES.map((t) => <MenuItem key={t} value={t}>{label(t)}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={2}>
        <TextField type="date" label="From" required fullWidth value={f.start_date} slotProps={{ inputLabel: { shrink: true } }}
          onChange={(e) => setF({ ...f, start_date: e.target.value, end_date: f.end_date || e.target.value })} />
        <TextField type="date" label="To" required fullWidth value={f.end_date} slotProps={{ inputLabel: { shrink: true } }}
          onChange={(e) => setF({ ...f, end_date: e.target.value })} />
      </Stack>
      <TextField label="Note" value={f.note} onChange={(e) => setF({ ...f, note: e.target.value })} />
    </FormDialog>
  )
}
