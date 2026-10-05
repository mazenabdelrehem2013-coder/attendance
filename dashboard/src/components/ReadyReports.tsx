import DownloadIcon from '@mui/icons-material/Download'
import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Chip from '@mui/material/Chip'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'

import { ApiError, apiDownload, apiGet } from '../api/client'
import type { ReadyReport, ReadyReportList } from '../api/scheduleTypes'

const size = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`)

/** Files created by scheduled reports (HR: company-wide, manager: own team). */
export function ReadyReports() {
  const list = useQuery({ queryKey: ['ready-reports'], queryFn: () => apiGet<ReadyReportList>('/reports/ready', { limit: '50' }) })
  const [error, setError] = useState<string | null>(null)

  async function download(r: ReadyReport) {
    setError(null)
    try {
      await apiDownload(`/reports/ready/${r.id}/download`, {}, r.filename)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Download failed.')
    }
  }

  return (
    <Stack spacing={1}>
      <Typography variant="h6">Ready reports</Typography>
      <Typography variant="body2" color="text.secondary">
        Created automatically by scheduled reports{list.data ? ` and kept for ${list.data.keep_days} days` : ''}.
      </Typography>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Report</TableCell><TableCell>Period</TableCell><TableCell>Covers</TableCell>
            <TableCell>Created</TableCell><TableCell>File</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {list.data?.items.map((r) => (
              <TableRow key={r.id} hover>
                <TableCell>{r.title}</TableCell>
                <TableCell>{r.period}</TableCell>
                <TableCell>{r.scope}</TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{new Date(r.created_at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</TableCell>
                <TableCell><Chip size="small" label={r.format === 'EXCEL' ? 'Excel' : 'PDF'} /> {size(r.size_bytes)}</TableCell>
                <TableCell>
                  <Button size="small" startIcon={<DownloadIcon />} aria-label={`Download ${r.filename}`} onClick={() => download(r)}>
                    Download
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {list.data?.items.length === 0 && (
              <TableRow><TableCell colSpan={6}>
                <Typography color="text.secondary" sx={{ py: 1, textAlign: 'center' }}>No ready reports yet.</Typography>
              </TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
    </Stack>
  )
}
