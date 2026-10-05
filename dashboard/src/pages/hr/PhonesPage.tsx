import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import Typography from '@mui/material/Typography'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { apiGet, apiPost, ApiError } from '../../api/client'
import type { Device, Page } from '../../api/hrTypes'

const when = (iso: string | null) =>
  iso ? new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Africa/Lagos' }).format(new Date(iso)) : '—'

const STATUS_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  ACTIVE: 'success', PENDING_APPROVAL: 'warning', REJECTED: 'error', DEACTIVATED: 'default', REREGISTRATION_REQUIRED: 'default',
}

export function PhonesPage() {
  const [tab, setTab] = useState<'PENDING_APPROVAL' | 'ALL'>('PENDING_APPROVAL')
  const queryClient = useQueryClient()
  const devices = useQuery({
    queryKey: ['devices', tab],
    queryFn: () => apiGet<Page<Device>>('/devices', { status: tab === 'ALL' ? undefined : tab, page_size: '200' }),
  })
  const act = useMutation({
    mutationFn: ({ id, action }: { id: string; action: 'approve' | 'reject' | 'deactivate' }) => {
      const note = action === 'approve' ? null : prompt('Note (optional):') ?? null
      return apiPost(`/devices/${id}/${action}`, { note })
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['devices'] }),
  })

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Phones</Typography>
      <Typography color="text.secondary">
        Each employee can check in only from one approved phone, and one phone can belong to only one employee.
        Approving a new phone switches off the employee's previous phone.
      </Typography>
      {act.error && <Alert severity="error">{act.error instanceof ApiError ? act.error.message : 'Failed'}</Alert>}
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="PENDING_APPROVAL" label="Waiting for approval" />
        <Tab value="ALL" label="All phones" />
      </Tabs>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Employee</TableCell><TableCell>Phone</TableCell><TableCell>Android</TableCell><TableCell>App</TableCell>
            <TableCell>Requested</TableCell><TableCell>Last used</TableCell><TableCell>Status</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {devices.data?.items.map((d) => (
              <TableRow key={d.id} hover>
                <TableCell>{d.employee_name} ({d.employee_code})</TableCell>
                <TableCell>{d.device_model ?? '—'}</TableCell>
                <TableCell>{d.os_version ?? '—'}</TableCell>
                <TableCell>{d.app_version ?? '—'}</TableCell>
                <TableCell>{when(d.requested_at)}</TableCell>
                <TableCell>{when(d.last_seen_at)}</TableCell>
                <TableCell><Chip size="small" label={d.status.replaceAll('_', ' ').toLowerCase()} color={STATUS_COLOR[d.status] ?? 'default'} /></TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {d.status === 'PENDING_APPROVAL' && (
                    <>
                      <Button size="small" color="success" variant="contained" onClick={() => act.mutate({ id: d.id, action: 'approve' })}>Approve</Button>{' '}
                      <Button size="small" color="error" onClick={() => act.mutate({ id: d.id, action: 'reject' })}>Reject</Button>
                    </>
                  )}
                  {d.status === 'ACTIVE' && (
                    <Button size="small" color="error" onClick={() => confirm(`Switch off ${d.employee_name}'s phone?`) && act.mutate({ id: d.id, action: 'deactivate' })}>
                      Deactivate
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {devices.data?.items.length === 0 && (
              <TableRow><TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>No phones here.</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  )
}
