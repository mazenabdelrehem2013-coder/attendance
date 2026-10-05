import FingerprintIcon from '@mui/icons-material/Fingerprint'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useState, type FormEvent } from 'react'

import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthProvider'

export function LoginPage({ notice }: { notice?: string }) {
  const { login } = useAuth()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(e: FormEvent) {
    e.preventDefault()
    if (!identifier.trim() || !password) {
      setError('Enter your email or employee ID and your password.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await login(identifier.trim(), password)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', bgcolor: 'grey.100', p: 2 }}>
      <Paper component="form" onSubmit={submit} sx={{ p: 4, width: '100%', maxWidth: 400 }} elevation={3}>
        <Box sx={{ textAlign: 'center', mb: 3 }}>
          <FingerprintIcon color="primary" sx={{ fontSize: 56 }} />
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Attendance Dashboard</Typography>
          <Typography variant="body2" color="text.secondary">For managers, HR and administrators</Typography>
        </Box>
        {notice && !error && <Alert severity="warning" sx={{ mb: 2 }}>{notice}</Alert>}
        {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
        <TextField label="Email or employee ID" fullWidth margin="normal" autoFocus autoComplete="username"
          value={identifier} onChange={(e) => setIdentifier(e.target.value)} />
        <TextField label="Password" type="password" fullWidth margin="normal" autoComplete="current-password"
          value={password} onChange={(e) => setPassword(e.target.value)} />
        <Button type="submit" variant="contained" size="large" fullWidth sx={{ mt: 2 }} disabled={busy}>
          {busy ? 'Logging in…' : 'Log in'}
        </Button>
      </Paper>
    </Box>
  )
}
