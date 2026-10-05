import AddIcon from '@mui/icons-material/Add'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { apiGet, apiPost } from '../../api/client'
import type { Location, QrDisplay } from '../../api/hrTypes'
import { FormDialog, SecretDialog } from '../../components/FormDialog'

function lastContact(iso: string | null) {
  if (!iso) return { label: 'never', color: 'default' as const }
  const minutes = (Date.now() - new Date(iso).getTime()) / 60000
  if (minutes < 2) return { label: 'online', color: 'success' as const }
  return { label: `${Math.round(minutes)} min ago`, color: 'warning' as const }
}

export function QrScreensPage() {
  const queryClient = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [key, setKey] = useState<{ label: string; value: string } | null>(null)
  const displays = useQuery({ queryKey: ['qr-displays'], queryFn: () => apiGet<QrDisplay[]>('/qr-displays'), refetchInterval: 30_000 })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['qr-displays'] })

  async function rotate(d: QrDisplay) {
    if (!confirm(`Give "${d.display_label}" a new key? The screen stops working until the new key is entered on it.`)) return
    const r = await apiPost<QrDisplay>(`/qr-displays/${d.id}/rotate-key`)
    refresh()
    setKey({ label: r.display_label, value: r.display_key! })
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Office QR screens</Typography>
      <Typography color="text.secondary">
        A screen or tablet in the office shows a QR code that changes every 30 seconds. To use it, open{' '}
        <b>{window.location.origin}/qr-display</b> on that screen and enter the screen's key. Then turn on
        "GPS + QR" for that location under Settings.
      </Typography>
      <Box><Button variant="contained" startIcon={<AddIcon />} onClick={() => setAdding(true)}>Add screen</Button></Box>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Screen</TableCell><TableCell>Location</TableCell><TableCell>Changes every</TableCell>
            <TableCell>Last contact</TableCell><TableCell>Status</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {displays.data?.map((d) => {
              const contact = lastContact(d.last_heartbeat_at)
              return (
                <TableRow key={d.id} hover>
                  <TableCell>{d.display_label}</TableCell>
                  <TableCell>{d.location_name}</TableCell>
                  <TableCell>{d.rotation_seconds} s</TableCell>
                  <TableCell><Chip size="small" label={contact.label} color={contact.color} /></TableCell>
                  <TableCell><Chip size="small" label={d.is_active ? 'Enabled' : 'Disabled'} color={d.is_active ? 'success' : 'default'} /></TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Button size="small" onClick={() => rotate(d)}>New key</Button>
                    <Button size="small" onClick={async () => { await apiPost(`/qr-displays/${d.id}/${d.is_active ? 'disable' : 'enable'}`); refresh() }}>
                      {d.is_active ? 'Disable' : 'Enable'}
                    </Button>
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </Paper>
      {adding && <AddScreenDialog onClose={() => setAdding(false)} onCreated={(d) => { refresh(); setKey({ label: d.display_label, value: d.display_key! }) }} />}
      {key && (
        <SecretDialog open title={`Key for "${key.label}"`} label="display key" value={key.value}
          note={`Shown only once. On the office screen, open ${window.location.origin}/qr-display and enter this key.`}
          onClose={() => setKey(null)} />
      )}
    </Stack>
  )
}

function AddScreenDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (d: QrDisplay) => void }) {
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const [location, setLocation] = useState('')
  const [label, setLabel] = useState('Reception screen')
  return (
    <FormDialog open title="Add office screen" submitLabel="Create" onClose={onClose}
      onSubmit={async () => onCreated(await apiPost<QrDisplay>('/qr-displays', { location_id: location, display_label: label }))}>
      <TextField select label="Location" required value={location} onChange={(e) => setLocation(e.target.value)}>
        {locations.data?.map((l) => <MenuItem key={l.id} value={l.id}>{l.name}</MenuItem>)}
      </TextField>
      <TextField label="Screen name" required value={label} onChange={(e) => setLabel(e.target.value)} />
    </FormDialog>
  )
}
