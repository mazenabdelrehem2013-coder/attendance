import AddIcon from '@mui/icons-material/Add'
import Autocomplete from '@mui/material/Autocomplete'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { apiGet, apiPost, apiPut } from '../../api/client'
import type { Department, Employee, Location, ManagerOption, Page } from '../../api/hrTypes'
import { useCurrentUser } from '../../auth/AuthProvider'
import { FormDialog, SecretDialog } from '../../components/FormDialog'

const ROLES = ['EMPLOYEE', 'MANAGER', 'HR', 'ADMIN'] as const

function useLookups() {
  const departments = useQuery({ queryKey: ['departments'], queryFn: () => apiGet<Department[]>('/departments') })
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const managers = useQuery({ queryKey: ['managers'], queryFn: () => apiGet<ManagerOption[]>('/managers') })
  return {
    departments: departments.data?.filter((d) => d.is_active) ?? [],
    locations: locations.data ?? [],
    managers: managers.data ?? [],
  }
}

export function EmployeesPage() {
  const me = useCurrentUser()
  const queryClient = useQueryClient()
  const [q, setQ] = useState('')
  const [editing, setEditing] = useState<Employee | 'new' | null>(null)
  const [placing, setPlacing] = useState<Employee | null>(null)
  const [secret, setSecret] = useState<{ title: string; value: string } | null>(null)
  const employees = useQuery({
    queryKey: ['employees', q],
    queryFn: () => apiGet<Page<Employee>>('/employees', { q: q.trim() || undefined, page_size: '200' }),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['employees'] })

  async function resetPassword(e: Employee) {
    if (!confirm(`Give ${e.full_name} a new temporary password? They will be logged out everywhere.`)) return
    const r = await apiPost<{ temporary_password: string }>(`/employees/${e.id}/reset-password`)
    setSecret({ title: `New temporary password for ${e.full_name}`, value: r.temporary_password })
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Typography variant="h5" sx={{ fontWeight: 700, flexGrow: 1 }}>Employees</Typography>
        <TextField size="small" label="Search name, ID or email" value={q} onChange={(e) => setQ(e.target.value)} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={() => setEditing('new')}>Add employee</Button>
      </Stack>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Name</TableCell><TableCell>Employee ID</TableCell><TableCell>Email</TableCell>
              <TableCell>Role</TableCell><TableCell>Department</TableCell><TableCell>Manager</TableCell>
              <TableCell>Locations</TableCell><TableCell>Status</TableCell><TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {employees.data?.items.map((e) => (
              <TableRow key={e.id} hover>
                <TableCell>{e.full_name}</TableCell>
                <TableCell>{e.employee_code}</TableCell>
                <TableCell>{e.email}</TableCell>
                <TableCell>{e.role}</TableCell>
                <TableCell>{e.department?.name ?? '—'}</TableCell>
                <TableCell>{e.manager?.name ?? '—'}</TableCell>
                <TableCell>{e.locations.map((l) => l.name + (l.is_primary && e.locations.length > 1 ? ' ★' : '')).join(', ') || '—'}</TableCell>
                <TableCell>
                  <Chip size="small" label={!e.is_active ? 'Login off' : e.employment_status.toLowerCase()}
                    color={e.employment_status === 'ACTIVE' && e.is_active ? 'success' : 'default'} />
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  <Button size="small" onClick={() => setEditing(e)}>Edit</Button>
                  <Button size="small" onClick={() => setPlacing(e)}>Locations</Button>
                  {e.user_id !== me.id && <Button size="small" onClick={() => resetPassword(e)}>Reset password</Button>}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
      {editing && (
        <EmployeeDialog employee={editing === 'new' ? null : editing} onClose={() => setEditing(null)}
          onSaved={(temp, name) => { refresh(); if (temp) setSecret({ title: `Temporary password for ${name}`, value: temp }) }} />
      )}
      {placing && <LocationsDialog employee={placing} onClose={() => setPlacing(null)} onSaved={refresh} />}
      {secret && (
        <SecretDialog open title={secret.title} label="temporary password" value={secret.value}
          note="Shown only once. Give it to the employee privately; they must choose their own password at first login."
          onClose={() => setSecret(null)} />
      )}
    </Stack>
  )
}

function EmployeeDialog({ employee, onClose, onSaved }: {
  employee: Employee | null; onClose: () => void; onSaved: (tempPassword: string | null, name: string) => void
}) {
  const me = useCurrentUser()
  const { departments, locations, managers } = useLookups()
  const [form, setForm] = useState({
    full_name: employee?.full_name ?? '',
    employee_code: employee?.employee_code ?? '',
    email: employee?.email ?? '',
    phone: employee?.phone ?? '',
    role: employee?.role ?? 'EMPLOYEE',
    department_id: employee?.department?.id ?? '',
    manager_id: employee?.manager?.id ?? '',
    employment_status: employee?.employment_status ?? 'ACTIVE',
    is_active: employee?.is_active ?? true,
    location_ids: [] as string[],
  })
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value })
  const roles = me.role === 'ADMIN' ? ROLES : (['EMPLOYEE', 'MANAGER'] as const)
  const isSelf = employee?.user_id === me.id

  async function save() {
    if (employee) {
      await apiPut(`/employees/${employee.id}`, {
        full_name: form.full_name, email: form.email, phone: form.phone || null,
        department_id: form.department_id || null, manager_id: form.manager_id || null,
        ...(isSelf ? {} : { role: form.role, employment_status: form.employment_status, is_active: form.is_active }),
      })
      onSaved(null, form.full_name)
    } else {
      if (!form.location_ids.length) throw new Error('Choose at least one location where this person may check in.')
      const r = await apiPost<{ temporary_password: string }>('/employees', {
        full_name: form.full_name, employee_code: form.employee_code, email: form.email,
        phone: form.phone || null, role: form.role, department_id: form.department_id || null,
        manager_id: form.manager_id || null, location_ids: form.location_ids,
      })
      onSaved(r.temporary_password, form.full_name)
    }
  }

  return (
    <FormDialog open title={employee ? `Edit ${employee.full_name}` : 'Add employee'} onClose={onClose} onSubmit={save}
      submitLabel={employee ? 'Save' : 'Create'}>
      <TextField label="Full name" required value={form.full_name} onChange={set('full_name')} />
      <TextField label="Employee ID" required disabled={!!employee} value={form.employee_code} onChange={set('employee_code')}
        helperText={employee ? 'The employee ID can’t be changed.' : 'e.g. EMP-0123'} />
      <TextField label="Email" type="email" required value={form.email} onChange={set('email')} />
      <TextField label="Phone" value={form.phone} onChange={set('phone')} />
      <TextField select label="Role" value={form.role} onChange={set('role')} disabled={isSelf}
        helperText={me.role !== 'ADMIN' ? 'Only an administrator can give HR or Admin access.' : undefined}>
        {roles.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
        {!roles.includes(form.role as never) && <MenuItem value={form.role}>{form.role}</MenuItem>}
      </TextField>
      <TextField select label="Department" value={form.department_id} onChange={set('department_id')}>
        <MenuItem value="">—</MenuItem>
        {departments.map((d) => <MenuItem key={d.id} value={d.id}>{d.name}</MenuItem>)}
      </TextField>
      <TextField select label="Manager" value={form.manager_id} onChange={set('manager_id')}>
        <MenuItem value="">—</MenuItem>
        {managers.map((m) => <MenuItem key={m.id} value={m.id}>{m.name} ({m.team_size})</MenuItem>)}
      </TextField>
      {!employee && (
        <Autocomplete multiple options={locations.filter((l) => l.is_active)} getOptionLabel={(l) => l.name}
          onChange={(_, v) => setForm({ ...form, location_ids: v.map((l) => l.id) })}
          renderInput={(p) => <TextField {...p} label="Check-in locations (first = main)" />} />
      )}
      {employee && !isSelf && (
        <>
          <TextField select label="Employment status" value={form.employment_status} onChange={set('employment_status')}
            helperText="Suspended or terminated people are logged out and can't log in.">
            <MenuItem value="ACTIVE">Active</MenuItem>
            <MenuItem value="SUSPENDED">Suspended</MenuItem>
            <MenuItem value="TERMINATED">Terminated</MenuItem>
          </TextField>
          <FormControlLabel label="Can log in" control={
            <Switch checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} />} />
        </>
      )}
    </FormDialog>
  )
}

function LocationsDialog({ employee, onClose, onSaved }: { employee: Employee; onClose: () => void; onSaved: () => void }) {
  const { locations } = useLookups()
  const active = locations.filter((l) => l.is_active)
  const [chosen, setChosen] = useState<string[]>(
    [...employee.locations].sort((a, b) => Number(b.is_primary) - Number(a.is_primary)).map((l) => l.location_id))
  const selected = chosen.map((id) => active.find((l) => l.id === id)).filter((l): l is Location => !!l)

  return (
    <FormDialog open title={`Check-in locations – ${employee.full_name}`} onClose={onClose}
      onSubmit={async () => { await apiPut(`/employees/${employee.id}/locations`, { location_ids: chosen }); onSaved() }}>
      <Typography variant="body2" color="text.secondary">
        The employee can check in only at these offices. The first one is their main location.
      </Typography>
      <Autocomplete multiple options={active} value={selected} getOptionLabel={(l) => l.name}
        isOptionEqualToValue={(a, b) => a.id === b.id}
        onChange={(_, v) => setChosen(v.map((l) => l.id))}
        renderInput={(p) => <TextField {...p} label="Locations" />} />
    </FormDialog>
  )
}
