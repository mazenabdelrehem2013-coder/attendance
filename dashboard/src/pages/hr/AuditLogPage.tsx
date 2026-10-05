import DownloadIcon from '@mui/icons-material/Download'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TablePagination from '@mui/material/TablePagination'
import TableRow from '@mui/material/TableRow'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiDownloadPost, apiGet } from '../../api/client'
import type { AuditLogDetail, AuditLogItem, ChainResult } from '../../api/securityTypes'
import { todayIso } from '../../lib/format'
import { ChainStatus } from './SecurityPage'

const when = (iso: string) => new Date(iso).toLocaleString(undefined, {
  day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit',
})
const pretty = (action: string) => action.charAt(0) + action.slice(1).toLowerCase().replaceAll('_', ' ')

export function AuditLogPage() {
  const today = todayIso()
  const [from, setFrom] = useState(`${today.slice(0, 8)}01`)
  const [to, setTo] = useState(today)
  const [action, setAction] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(0)
  const [open, setOpen] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)

  const actions = useQuery({ queryKey: ['audit-actions'], queryFn: () => apiGet<string[]>('/audit-logs/actions') })
  const chain = useQuery({ queryKey: ['audit-chain'], queryFn: () => apiGet<ChainResult | null>('/audit-logs/chain') })
  const params = { from, to, action: action || undefined, q: q || undefined, limit: '50', offset: String(page * 50) }
  const logs = useQuery({ queryKey: ['audit-logs', params], queryFn: () => apiGet<{ items: AuditLogItem[]; total: number }>('/audit-logs', params) })

  async function exportExcel() {
    setExporting(true)
    setError(null)
    try {
      await apiDownloadPost('/audit-logs/export', { date_from: from, date_to: to, action: action || null, q: q || null })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Export failed.')
    } finally {
      setExporting(false)
    }
  }

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Audit log</Typography>
      <Typography color="text.secondary">
        Every change made in the system: who, what, when and from where. Entries can never be edited or deleted.
      </Typography>
      <ChainStatus chain={chain.data} />
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap', alignItems: 'center' }}>
          <TextField type="date" size="small" label="From" value={from} slotProps={{ inputLabel: { shrink: true } }}
            onChange={(e) => { if (e.target.value) { setFrom(e.target.value); setPage(0) } }} />
          <TextField type="date" size="small" label="To" value={to} slotProps={{ inputLabel: { shrink: true } }}
            onChange={(e) => { if (e.target.value) { setTo(e.target.value); setPage(0) } }} />
          <TextField select size="small" label="Action" value={action} sx={{ minWidth: 240 }}
            slotProps={{ select: { displayEmpty: true }, inputLabel: { shrink: true } }}
            onChange={(e) => { setAction(e.target.value); setPage(0) }}>
            <MenuItem value="">All actions</MenuItem>
            {actions.data?.map((a) => <MenuItem key={a} value={a}>{pretty(a)}</MenuItem>)}
          </TextField>
          <TextField size="small" label="Search person or object" value={q} onChange={(e) => { setQ(e.target.value); setPage(0) }} />
          <Button variant="outlined" startIcon={<DownloadIcon />} disabled={exporting} onClick={exportExcel}>
            {exporting ? 'Preparing…' : 'Export Excel'}
          </Button>
        </Stack>
      </Paper>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>#</TableCell><TableCell>When</TableCell><TableCell>Who</TableCell><TableCell>What</TableCell>
            <TableCell>Changed</TableCell><TableCell>From</TableCell>
          </TableRow></TableHead>
          <TableBody>
            {logs.data?.items.map((l) => (
              <TableRow key={l.id} hover sx={{ cursor: 'pointer' }} onClick={() => setOpen(l.id)}>
                <TableCell>{l.seq}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{when(l.created_at)}</TableCell>
                <TableCell>{l.actor_name ?? l.actor}{l.actor_role && <Typography variant="caption" color="text.secondary"> · {l.actor_role}</Typography>}</TableCell>
                <TableCell>{pretty(l.action)}{l.object_type && <Typography variant="body2" color="text.secondary">{l.object_type}</Typography>}</TableCell>
                <TableCell>{l.changed.slice(0, 4).map((c) => <Chip key={c} size="small" label={c} sx={{ mr: 0.5, mb: 0.5 }} />)}{l.changed.length > 4 && `+${l.changed.length - 4}`}</TableCell>
                <TableCell>{l.ip_address ?? '—'}</TableCell>
              </TableRow>
            ))}
            {logs.data?.items.length === 0 && (
              <TableRow><TableCell colSpan={6}><Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>No entries.</Typography></TableCell></TableRow>
            )}
          </TableBody>
        </Table>
        <TablePagination component="div" count={logs.data?.total ?? 0} page={page} rowsPerPage={50} rowsPerPageOptions={[50]}
          onPageChange={(_, p) => setPage(p)} />
      </Paper>
      {open && <EntryDialog id={open} onClose={() => setOpen(null)} />}
    </Stack>
  )
}

function show(v: unknown): string {
  if (v === undefined) return ''
  return typeof v === 'string' ? v : JSON.stringify(v)
}

function EntryDialog({ id, onClose }: { id: string; onClose: () => void }) {
  const entry = useQuery({ queryKey: ['audit-log', id], queryFn: () => apiGet<AuditLogDetail>(`/audit-logs/${id}`) })
  const e = entry.data
  const keys = e ? Array.from(new Set([...Object.keys(e.old_value ?? {}), ...Object.keys(e.new_value ?? {})])).sort() : []
  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{e ? `#${e.seq} · ${pretty(e.action)}` : 'Audit entry'}</DialogTitle>
      <DialogContent>
        {e && (
          <Stack spacing={2}>
            <Typography>
              {when(e.created_at)} · {e.actor_name ?? e.actor} ({e.actor_role ?? 'system'}) · {e.object_type ?? ''} {e.object_id ?? ''}
            </Typography>
            {keys.length > 0 && (
              <Table size="small">
                <TableHead><TableRow><TableCell>Field</TableCell><TableCell>Before</TableCell><TableCell>After</TableCell></TableRow></TableHead>
                <TableBody>
                  {keys.map((k) => {
                    const before = show(e.old_value?.[k])
                    const after = show(e.new_value?.[k])
                    return (
                      <TableRow key={k} sx={{ bgcolor: before !== after ? 'action.hover' : undefined }}>
                        <TableCell sx={{ fontWeight: before !== after ? 600 : 400 }}>{k}</TableCell>
                        <TableCell sx={{ wordBreak: 'break-word' }}>{before}</TableCell>
                        <TableCell sx={{ wordBreak: 'break-word' }}>{after}</TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            )}
            <Typography variant="body2" color="text.secondary">
              Address: {e.ip_address ?? '—'} · Request: {e.request_id ?? '—'}<br />
              Device: {e.user_agent ?? '—'}<br />
              Fingerprint: <code>{e.row_hash.slice(0, 16)}…</code>
            </Typography>
          </Stack>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Close</Button></DialogActions>
    </Dialog>
  )
}
