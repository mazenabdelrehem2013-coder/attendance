import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Paper from '@mui/material/Paper'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import QRCode from 'qrcode'
import { useEffect, useState } from 'react'

/**
 * Full-screen page for the office screen/tablet (open /qr-display). No user login: the screen
 * uses its own display key (created by HR), kept in this browser only. The page fetches the
 * current code every few seconds; the signing secret never leaves the server.
 */
const STORAGE_KEY = 'attendance.qrDisplayKey'

function readKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? ''
  } catch {
    return ''
  }
}

export function QrDisplayPage() {
  const [key, setKey] = useState(readKey)
  const [input, setInput] = useState('')
  const [qr, setQr] = useState<{ image: string; location: string; expires: number } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    if (!key) return
    let stopped = false
    async function load() {
      try {
        const r = await fetch('/api/v1/qr/current', { headers: { 'X-Display-Key': key } })
        if (r.status === 401) {
          setError('This screen key is not valid any more. Ask HR for a new key.')
          setQr(null)
          return
        }
        if (!r.ok) throw new Error()
        const body = await r.json()
        const image = await QRCode.toDataURL(body.token, { width: 640, margin: 2, errorCorrectionLevel: 'M' })
        if (!stopped) {
          setQr({ image, location: body.location_name, expires: new Date(body.expires_at).getTime() })
          setError(null)
        }
      } catch {
        if (!stopped) setError('No connection to the server – retrying…')
      }
    }
    load()
    const poll = setInterval(load, 3000)
    const tick = setInterval(() => setNow(Date.now()), 500)
    return () => { stopped = true; clearInterval(poll); clearInterval(tick) }
  }, [key])

  function saveKey() {
    try { localStorage.setItem(STORAGE_KEY, input.trim()) } catch { /* private window: keep in memory only */ }
    setKey(input.trim())
  }

  if (!key) {
    return (
      <Box sx={{ minHeight: '100vh', display: 'grid', placeItems: 'center', p: 2 }}>
        <Paper sx={{ p: 4, maxWidth: 480 }}>
          <Typography variant="h5" gutterBottom>Office QR screen</Typography>
          <Typography color="text.secondary" gutterBottom>Enter the screen key HR gave you (starts with "qrd_").</Typography>
          <TextField fullWidth label="Screen key" value={input} onChange={(e) => setInput(e.target.value)} sx={{ my: 2 }} />
          <Button variant="contained" fullWidth disabled={!input.trim().startsWith('qrd_')} onClick={saveKey}>Start</Button>
        </Paper>
      </Box>
    )
  }

  const seconds = qr ? Math.max(0, Math.ceil((qr.expires - now) / 1000)) : 0
  return (
    <Box sx={{ minHeight: '100vh', bgcolor: '#fff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', p: 2 }}>
      {qr && <Typography variant="h3" sx={{ fontWeight: 700, mb: 2 }}>{qr.location}</Typography>}
      {qr ? <img src={qr.image} alt="Attendance QR code" style={{ width: 'min(80vh, 90vw)', height: 'min(80vh, 90vw)' }} />
        : <Typography variant="h5" color="text.secondary">Loading…</Typography>}
      <Typography variant="h5" sx={{ mt: 2 }}>Scan with the Attendance app · new code in {seconds} s</Typography>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      <Button size="small" sx={{ mt: 4, opacity: 0.4 }} onClick={() => {
        try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
        setKey('')
      }}>Change key</Button>
    </Box>
  )
}
