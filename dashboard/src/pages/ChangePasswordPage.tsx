import Alert from '@mui/material/Alert'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

export function ChangePasswordPage({ forced = false }: { forced?: boolean }) {
  const { changePassword, logout } = useAuth()
  const navigate = useNavigate()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (next.length < 10) return setError('The new password must be at least 10 characters.')
    if (next !== confirm) return setError('The new passwords are not the same.')
    setBusy(true)
    setError(null)
    try {
      await changePassword(current, next)
      if (!forced) navigate('/')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Paper component="form" onSubmit={submit} sx={{ p: 4, maxWidth: 440, mx: 'auto', mt: forced ? 8 : 0 }}>
      <Typography variant="h6" gutterBottom>Change password</Typography>
      {forced && <Alert severity="info" sx={{ mb: 2 }}>Please choose your own password before continuing.</Alert>}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      <TextField label={forced ? 'Temporary password' : 'Current password'} type="password" fullWidth margin="normal"
        value={current} onChange={(e) => setCurrent(e.target.value)} autoComplete="current-password" />
      <TextField label="New password" type="password" fullWidth margin="normal" helperText="At least 10 characters"
        value={next} onChange={(e) => setNext(e.target.value)} autoComplete="new-password" />
      <TextField label="Repeat new password" type="password" fullWidth margin="normal"
        value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
      <Button type="submit" variant="contained" fullWidth sx={{ mt: 2 }} disabled={busy}>Save password</Button>
      {forced && <Button fullWidth sx={{ mt: 1 }} onClick={logout}>Log out</Button>}
    </Paper>
  )
}
