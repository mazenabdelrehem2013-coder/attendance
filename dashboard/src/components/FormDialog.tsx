import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Dialog from '@mui/material/Dialog'
import DialogActions from '@mui/material/DialogActions'
import DialogContent from '@mui/material/DialogContent'
import DialogTitle from '@mui/material/DialogTitle'
import Stack from '@mui/material/Stack'
import { useState, type FormEvent, type ReactNode } from 'react'

import { ApiError } from '../api/client'

/** A pop-up form: shows server errors, disables itself while saving, closes on success. */
export function FormDialog({
  open, title, submitLabel = 'Save', onClose, onSubmit, children, maxWidth = 'sm',
}: {
  open: boolean
  title: string
  submitLabel?: string
  onClose: () => void
  onSubmit: () => Promise<unknown>
  children: ReactNode
  maxWidth?: 'xs' | 'sm' | 'md'
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await onSubmit()
      onClose()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : (err as Error).message || 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth={maxWidth}>
      <form onSubmit={submit}>
        <DialogTitle>{title}</DialogTitle>
        <DialogContent>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
          <Stack spacing={2} sx={{ pt: 1 }}>{children}</Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={busy}>Cancel</Button>
          <Button type="submit" variant="contained" disabled={busy}>{submitLabel}</Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}

/** Shows a one-time secret (temporary password, screen key) with a clear warning. */
export function SecretDialog({ open, title, label, value, note, onClose }: {
  open: boolean; title: string; label: string; value: string; note: string; onClose: () => void
}) {
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>{title}</DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>{note}</Alert>
        <Stack direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <code style={{ fontSize: 18, padding: '8px 12px', background: '#f3f3f3', borderRadius: 6, flexGrow: 1, wordBreak: 'break-all' }}
            aria-label={label}>{value}</code>
          <Button onClick={() => navigator.clipboard?.writeText(value)}>Copy</Button>
        </Stack>
      </DialogContent>
      <DialogActions><Button variant="contained" onClick={onClose}>Done</Button></DialogActions>
    </Dialog>
  )
}
