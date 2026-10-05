import GppBadIcon from '@mui/icons-material/GppBad'
import VerifiedUserIcon from '@mui/icons-material/VerifiedUser'
import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Card from '@mui/material/Card'
import CardContent from '@mui/material/CardContent'
import Chip from '@mui/material/Chip'
import MenuItem from '@mui/material/MenuItem'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import Tab from '@mui/material/Tab'
import Table from '@mui/material/Table'
import TableBody from '@mui/material/TableBody'
import TableCell from '@mui/material/TableCell'
import TableHead from '@mui/material/TableHead'
import TableRow from '@mui/material/TableRow'
import Tabs from '@mui/material/Tabs'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { ApiError, apiGet, apiPost, apiPut } from '../../api/client'
import {
  EVENT_LABELS, SEVERITY_COLOR, days,
  type AlertItem, type ChainResult, type RetentionItem, type RuleInfo, type SecurityOverview,
} from '../../api/securityTypes'
import { useCurrentUser } from '../../auth/AuthProvider'
import { FormDialog } from '../../components/FormDialog'

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '—'

export function SecurityPage() {
  const [tab, setTab] = useState('overview')
  return (
    <Stack spacing={2}>
      <Typography variant="h5" sx={{ fontWeight: 700 }}>Security monitoring</Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)}>
        <Tab value="overview" label="Overview" />
        <Tab value="alerts" label="Alerts" />
        <Tab value="rules" label="Alert rules" />
        <Tab value="retention" label="Data retention" />
      </Tabs>
      {tab === 'overview' && <Overview />}
      {tab === 'alerts' && <Alerts />}
      {tab === 'rules' && <Rules />}
      {tab === 'retention' && <Retention />}
    </Stack>
  )
}

// --- Overview ---------------------------------------------------------------------------------

function Stat({ label, value, tone }: { label: string; value: number | string; tone?: string }) {
  return (
    <Card variant="outlined" sx={{ flex: 1, minWidth: 150 }}>
      <CardContent>
        <Typography variant="h4" sx={{ fontWeight: 700, color: tone }}>{value}</Typography>
        <Typography color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  )
}

export function ChainStatus({ chain }: { chain: ChainResult | null | undefined }) {
  const queryClient = useQueryClient()
  const [busy, setBusy] = useState(false)
  async function verify() {
    setBusy(true)
    try {
      await apiPost('/audit-logs/verify')
    } finally {
      setBusy(false)
      queryClient.invalidateQueries({ queryKey: ['security-overview'] })
      queryClient.invalidateQueries({ queryKey: ['audit-chain'] })
    }
  }
  const button = <Button size="small" onClick={verify} disabled={busy}>{busy ? 'Checking…' : 'Check now'}</Button>
  if (!chain) return <Alert severity="info" action={button}>The audit log has not been checked yet (it is checked every night).</Alert>
  return chain.ok ? (
    <Alert severity="success" icon={<VerifiedUserIcon />} action={button}>
      Audit log intact: {chain.rows_checked.toLocaleString()} entries checked, none changed or deleted ({when(chain.checked_at)}).
    </Alert>
  ) : (
    <Alert severity="error" icon={<GppBadIcon />} action={button}>
      Audit log tampering detected: {chain.problem} ({when(chain.checked_at)}). Contact your system administrator.
    </Alert>
  )
}

function Overview() {
  const overview = useQuery({ queryKey: ['security-overview'], queryFn: () => apiGet<SecurityOverview>('/security/overview') })
  const o = overview.data
  if (overview.error) return <Alert severity="error">{(overview.error as Error).message}</Alert>
  if (!o) return null
  const active = o.open_alerts.CRITICAL + o.open_alerts.HIGH + o.open_alerts.MEDIUM + o.open_alerts.LOW
  return (
    <Stack spacing={2}>
      <ChainStatus chain={o.chain} />
      <Typography color="text.secondary">Last 30 days ({o.date_from} – {o.date_to})</Typography>
      <Stack direction="row" spacing={2} useFlexGap sx={{ flexWrap: 'wrap' }}>
        <Stat label="Open alerts" value={active} tone={active ? '#c5221f' : undefined} />
        <Stat label="Security events" value={o.total_events} />
        <Stat label="Serious (high)" value={o.by_severity.HIGH + o.by_severity.CRITICAL} tone="#e37400" />
        <Stat label="Failed logins" value={o.failed_logins} />
        <Stat label="Accounts locked" value={o.locked_accounts} />
      </Stack>
      <Paper variant="outlined" sx={{ p: 2, height: 300 }}>
        <Typography sx={{ fontWeight: 600, mb: 1 }}>Security events per day</Typography>
        <ResponsiveContainer height="88%">
          <BarChart data={o.per_day.map((d) => ({ ...d, day: d.date.slice(5) }))}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="day" /><YAxis allowDecimals={false} /><Tooltip /><Legend />
            <Bar dataKey="low" name="Low" stackId="s" fill="#9aa0a6" />
            <Bar dataKey="medium" name="Medium" stackId="s" fill="#1a73e8" />
            <Bar dataKey="high" name="High" stackId="s" fill="#e37400" />
            <Bar dataKey="critical" name="Critical" stackId="s" fill="#c5221f" />
          </BarChart>
        </ResponsiveContainer>
      </Paper>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
        <TopList title="Most frequent events" rows={o.by_type.map((t) => ({ name: EVENT_LABELS[t.key] ?? t.key, count: t.count }))} />
        <TopList title="Employees with most serious events" rows={o.top_employees.map((t) => ({ name: `${t.label} (${t.key})`, count: t.count }))} />
        <TopList title="Failed logins by internet address" rows={o.top_ips.map((t) => ({ name: t.key, count: t.count }))} />
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Each event and its check details: <RouterLink to="/review">Suspicious activity → Security events</RouterLink>.
      </Typography>
    </Stack>
  )
}

function TopList({ title, rows }: { title: string; rows: { name: string; count: number }[] }) {
  return (
    <Paper variant="outlined" sx={{ flex: 1 }}>
      <Typography sx={{ fontWeight: 600, p: 1.5 }}>{title}</Typography>
      <Table size="small">
        <TableBody>
          {rows.map((r) => <TableRow key={r.name}><TableCell>{r.name}</TableCell><TableCell align="right">{r.count}</TableCell></TableRow>)}
          {rows.length === 0 && <TableRow><TableCell><Typography color="text.secondary">None</Typography></TableCell></TableRow>}
        </TableBody>
      </Table>
    </Paper>
  )
}

// --- Alerts -----------------------------------------------------------------------------------

function Alerts() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('active')
  const [handling, setHandling] = useState<{ alert: AlertItem; to: 'ACKNOWLEDGED' | 'RESOLVED' } | null>(null)
  const alerts = useQuery({ queryKey: ['security-alerts', status], queryFn: () => apiGet<{ items: AlertItem[]; total: number }>('/security/alerts', { status, limit: '200' }) })

  return (
    <>
      <TextField select size="small" label="Show" value={status} onChange={(e) => setStatus(e.target.value)} sx={{ width: 220 }}>
        <MenuItem value="active">Not resolved</MenuItem>
        <MenuItem value="RESOLVED">Resolved</MenuItem>
        <MenuItem value="all">All</MenuItem>
      </TextField>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow>
            <TableCell>Severity</TableCell><TableCell>Alert</TableCell><TableCell>Last seen</TableCell>
            <TableCell>Status</TableCell><TableCell />
          </TableRow></TableHead>
          <TableBody>
            {alerts.data?.items.map((a) => (
              <TableRow key={a.id} hover>
                <TableCell><Chip size="small" label={a.severity} color={SEVERITY_COLOR[a.severity]} /></TableCell>
                <TableCell>
                  <Typography sx={{ fontWeight: 600 }}>{a.title}</Typography>
                  <Typography variant="body2" color="text.secondary">{a.rule_label} · first seen {when(a.first_seen_at)}</Typography>
                  {a.note && <Typography variant="body2">Note: {a.note}</Typography>}
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>{when(a.last_seen_at)}</TableCell>
                <TableCell>
                  {a.status === 'OPEN' ? 'Open' : a.status === 'ACKNOWLEDGED' ? `Being checked (${a.handled_by})` : `Resolved by ${a.handled_by}`}
                </TableCell>
                <TableCell sx={{ whiteSpace: 'nowrap' }}>
                  {a.status === 'OPEN' && <Button size="small" onClick={() => setHandling({ alert: a, to: 'ACKNOWLEDGED' })}>I'm checking it</Button>}
                  {a.status !== 'RESOLVED' && <Button size="small" onClick={() => setHandling({ alert: a, to: 'RESOLVED' })}>Resolve</Button>}
                </TableCell>
              </TableRow>
            ))}
            {alerts.data?.items.length === 0 && (
              <TableRow><TableCell colSpan={5}><Typography color="text.secondary" sx={{ py: 2, textAlign: 'center' }}>No alerts.</Typography></TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>
      {handling && <HandleDialog {...handling} onClose={() => setHandling(null)}
        onDone={() => { queryClient.invalidateQueries({ queryKey: ['security-alerts'] }); queryClient.invalidateQueries({ queryKey: ['badge-alerts'] }) }} />}
    </>
  )
}

function HandleDialog({ alert, to, onClose, onDone }: { alert: AlertItem; to: 'ACKNOWLEDGED' | 'RESOLVED'; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState('')
  return (
    <FormDialog open title={to === 'RESOLVED' ? 'Resolve alert' : 'Mark as being checked'} onClose={onClose}
      submitLabel={to === 'RESOLVED' ? 'Resolve' : 'Save'}
      onSubmit={async () => { await apiPost(`/security/alerts/${alert.id}`, { status: to, note: note || null }); onDone() }}>
      <Typography>{alert.title}</Typography>
      <TextField label={to === 'RESOLVED' ? 'What did you find or do? (required)' : 'Note (optional)'} value={note}
        onChange={(e) => setNote(e.target.value)} multiline minRows={3} required={to === 'RESOLVED'} />
    </FormDialog>
  )
}

// --- Rules ------------------------------------------------------------------------------------

function Rules() {
  const rules = useQuery({ queryKey: ['security-rules'], queryFn: () => apiGet<RuleInfo[]>('/security/rules') })
  return (
    <>
      <Typography color="text.secondary">Checked every minute. New alerts appear under the bell for HR and Admin.</Typography>
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Rule</TableCell><TableCell>Severity</TableCell><TableCell>What it looks for</TableCell></TableRow></TableHead>
          <TableBody>
            {rules.data?.map((r) => (
              <TableRow key={r.rule}>
                <TableCell sx={{ fontWeight: 600 }}>{r.label}</TableCell>
                <TableCell><Chip size="small" label={r.severity} color={SEVERITY_COLOR[r.severity]} /></TableCell>
                <TableCell>{r.description}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </>
  )
}

// --- Data retention ---------------------------------------------------------------------------

function Retention() {
  const user = useCurrentUser()
  const queryClient = useQueryClient()
  const items = useQuery({ queryKey: ['retention'], queryFn: () => apiGet<RetentionItem[]>('/retention') })
  const lastRun = useQuery({ queryKey: ['retention-last'], queryFn: () => apiGet<{ ran_at: string; results: Record<string, number> } | null>('/retention/last-run') })
  const [error, setError] = useState<string | null>(null)
  const isAdmin = user.role === 'ADMIN'

  async function save(item: RetentionItem, value: number) {
    setError(null)
    try {
      await apiPut(`/retention/${item.category}`, { retain_days: value })
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Saving failed.')
    }
    queryClient.invalidateQueries({ queryKey: ['retention'] })
  }

  return (
    <>
      <Typography color="text.secondary">
        Old data is removed automatically every night. {isAdmin ? '' : 'Only an Admin can change these periods.'}
        {lastRun.data && ` Last clean-up: ${when(lastRun.data.ran_at)}.`}
      </Typography>
      {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead><TableRow><TableCell>Data</TableCell><TableCell>Kept for</TableCell><TableCell>After that</TableCell></TableRow></TableHead>
          <TableBody>
            {items.data?.map((i) => (
              <TableRow key={i.category}>
                <TableCell sx={{ maxWidth: 420 }}>
                  <Typography sx={{ fontWeight: 600 }}>{i.label}</Typography>
                  <Typography variant="body2" color="text.secondary">{i.description}</Typography>
                </TableCell>
                <TableCell>
                  {isAdmin ? (
                    <TextField size="small" type="number" label="Days" defaultValue={i.retain_days} sx={{ width: 120 }}
                      slotProps={{ htmlInput: { min: i.min_days, 'aria-label': `${i.label} days` } }}
                      helperText={`${days(i.retain_days)} · min ${i.min_days}`}
                      onBlur={(e) => Number(e.target.value) !== i.retain_days && save(i, Number(e.target.value))} />
                  ) : days(i.retain_days)}
                </TableCell>
                <TableCell>{i.automatic ? 'Removed automatically' : <Box component="span" sx={{ color: 'text.secondary' }}>Kept (not removed automatically)</Box>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </>
  )
}
