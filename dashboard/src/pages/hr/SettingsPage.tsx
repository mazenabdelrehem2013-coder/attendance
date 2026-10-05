import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import FormControlLabel from '@mui/material/FormControlLabel'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Switch from '@mui/material/Switch'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { apiDelete, apiGet, apiPut, ApiError } from '../../api/client'
import type { Location, Policy, PolicyAction } from '../../api/hrTypes'

const ACTIONS: { key: keyof Policy; label: string; help: string }[] = [
  { key: 'on_outside_geofence', label: 'Outside the office radius', help: 'The GPS position is outside the allowed radius.' },
  { key: 'on_poor_accuracy', label: 'GPS signal too weak', help: 'Accuracy worse than the limit below.' },
  { key: 'on_stale_location', label: 'Old GPS reading', help: 'Reading older than the limit below, or taken before the request.' },
  { key: 'on_mock_location', label: 'Fake-GPS app detected', help: "Android reports the location comes from a 'mock location' app." },
  { key: 'on_integrity_fail', label: 'App / phone integrity failed', help: 'Google Play Integrity: modified app, rooted phone, emulator…' },
  { key: 'on_impossible_travel', label: 'Impossible travel speed', help: 'Faster than the limit below since the last check-in.' },
  { key: 'on_clock_skew', label: 'Phone clock changed', help: 'Phone time differs from the server by more than the limit below.' },
  { key: 'on_qr_fail', label: 'Office QR missing or invalid', help: 'Only when the location requires QR.' },
]

const ACTION_LABEL: Record<PolicyAction, string> = {
  ALLOW: 'Allow (record only)',
  FLAG: 'Flag for HR review',
  REJECT: 'Reject',
}

const NUMBERS: { key: keyof Policy; label: string; unit: string }[] = [
  { key: 'max_accuracy_m', label: 'Worst accepted GPS accuracy', unit: 'm' },
  { key: 'max_fix_age_s', label: 'Oldest accepted GPS reading', unit: 's' },
  { key: 'max_travel_speed_kmh', label: 'Highest believable travel speed', unit: 'km/h' },
  { key: 'max_clock_skew_s', label: 'Allowed phone clock difference', unit: 's' },
  { key: 'challenge_ttl_s', label: 'Time to complete a check-in', unit: 's' },
]

export function SettingsPage() {
  const queryClient = useQueryClient()
  const policies = useQuery({ queryKey: ['policies'], queryFn: () => apiGet<{ default: Policy; locations: Policy[] }>('/settings/attendance-policies') })
  const locations = useQuery({ queryKey: ['locations-all'], queryFn: () => apiGet<Location[]>('/locations') })
  const [target, setTarget] = useState('default')

  const overrides = policies.data?.locations ?? []
  const current = target === 'default' ? policies.data?.default
    : overrides.find((p) => p.location_id === target) ?? (policies.data ? { ...policies.data.default, location_id: target } : undefined)
  const hasOverride = overrides.some((p) => p.location_id === target)

  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Security settings</Typography>
      <Typography color="text.secondary">
        What happens when a check fails. "Flag" = recorded but doesn't count until HR approves (your company's choice).
        Every change is kept in the audit log.
      </Typography>
      <TextField select label="Rules for" value={target} onChange={(e) => setTarget(e.target.value)} sx={{ maxWidth: 400 }}>
        <MenuItem value="default">The whole company (default)</MenuItem>
        {locations.data?.map((l) => (
          <MenuItem key={l.id} value={l.id}>{l.name}{overrides.some((p) => p.location_id === l.id) ? ' – own rules' : ''}</MenuItem>
        ))}
      </TextField>
      {target !== 'default' && !hasOverride && (
        <Alert severity="info">This location uses the company rules. Changing anything below gives it its own rules.</Alert>
      )}
      {current && <PolicyForm key={target} policy={current} target={target} hasOverride={hasOverride}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ['policies'] })} />}
    </Stack>
  )
}

function PolicyForm({ policy, target, hasOverride, onSaved }: {
  policy: Policy; target: string; hasOverride: boolean; onSaved: () => void
}) {
  const [f, setF] = useState<Policy>(policy)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => setF(policy), [policy])

  async function save() {
    setMessage(null)
    const changes = Object.fromEntries(Object.entries(f).filter(([k, v]) => !['location_id', 'location_name'].includes(k) && policy[k as keyof Policy] !== v))
    if (!Object.keys(changes).length) return setMessage({ ok: true, text: 'Nothing changed.' })
    try {
      await apiPut(target === 'default' ? '/settings/attendance-policies/default' : `/settings/attendance-policies/locations/${target}`, changes)
      setMessage({ ok: true, text: 'Saved. The new rules apply to the next check-in.' })
      onSaved()
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : 'Saving failed.' })
    }
  }

  async function resetToCompany() {
    if (!confirm('Use the company rules for this location again?')) return
    await apiDelete(`/settings/attendance-policies/locations/${target}`)
    onSaved()
  }

  return (
    <Paper variant="outlined" sx={{ p: 3, maxWidth: 820 }}>
      <Stack spacing={3}>
        <TextField select label="Verification method" value={f.verification_mode}
          onChange={(e) => setF({ ...f, verification_mode: e.target.value as Policy['verification_mode'] })}
          helperText="GPS + QR needs a QR screen at this office (see QR screens).">
          <MenuItem value="GPS_ONLY">GPS only</MenuItem>
          <MenuItem value="GPS_QR">GPS + office QR code</MenuItem>
          <MenuItem value="GPS_QR_PLUS">GPS + QR + additional verification (future)</MenuItem>
        </TextField>

        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>When a check fails</Typography>
          <Stack spacing={1.5}>
            {ACTIONS.map((a) => (
              <Stack key={a.key} direction="row" spacing={2} sx={{ alignItems: 'center' }}>
                <Box sx={{ flexGrow: 1 }}>
                  <Typography>{a.label}</Typography>
                  <Typography variant="caption" color="text.secondary">{a.help}</Typography>
                </Box>
                <TextField select size="small" value={f[a.key] as string} sx={{ width: 220 }}
                  onChange={(e) => setF({ ...f, [a.key]: e.target.value })}>
                  {(['ALLOW', 'FLAG', 'REJECT'] as PolicyAction[]).map((x) => <MenuItem key={x} value={x}>{ACTION_LABEL[x]}</MenuItem>)}
                </TextField>
              </Stack>
            ))}
          </Stack>
        </Box>

        <Box>
          <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>Limits</Typography>
          <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))' }}>
            {NUMBERS.map((n) => (
              <TextField key={n.key} type="number" label={`${n.label} (${n.unit})`} value={f[n.key] as number}
                onChange={(e) => setF({ ...f, [n.key]: Number(e.target.value) })} />
            ))}
          </Box>
        </Box>

        <FormControlLabel
          control={<Switch checked={f.flagged_counts_before_review}
            onChange={(e) => setF({ ...f, flagged_counts_before_review: e.target.checked })} />}
          label="Count flagged attendance before HR has reviewed it (your company chose: off)" />

        {message && <Alert severity={message.ok ? 'success' : 'error'}>{message.text}</Alert>}
        <Stack direction="row" spacing={2}>
          <Button variant="contained" onClick={save}>Save</Button>
          {target !== 'default' && hasOverride && <Button color="error" onClick={resetToCompany}>Use company rules</Button>}
        </Stack>
      </Stack>
    </Paper>
  )
}
