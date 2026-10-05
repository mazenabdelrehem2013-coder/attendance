import Box from '@mui/material/Box'
import Card from '@mui/material/Card'
import CardActionArea from '@mui/material/CardActionArea'
import CardContent from '@mui/material/CardContent'
import Paper from '@mui/material/Paper'
import Stack from '@mui/material/Stack'
import TextField from '@mui/material/TextField'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useMemo, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

import { apiGet } from '../../api/client'
import type { HrOverview, TrendPoint } from '../../api/hrTypes'
import { longDate, todayIso } from '../../lib/format'

const COLORS = { present: '#2e7d32', late: '#ed6c02', absent: '#d32f2f', pending: '#8E44AD' }

function daysBefore(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() - days)
  return d.toISOString().slice(0, 10)
}

function ChartCard({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>{title}</Typography>
      <Box sx={{ height: 280 }}>{children}</Box>
    </Paper>
  )
}

export function HrOverviewPage() {
  const navigate = useNavigate()
  const [date, setDate] = useState(todayIso())
  const overview = useQuery({
    queryKey: ['hr-overview', date],
    queryFn: () => apiGet<HrOverview>('/hr/overview', { date }),
    refetchInterval: date === todayIso() ? 60_000 : false,
  })
  const trend = useQuery({
    queryKey: ['hr-trend', date],
    queryFn: () => apiGet<TrendPoint[]>('/hr/trend', { from: daysBefore(date, 89), to: date }),
  })

  const last30 = useMemo(() => (trend.data ?? []).slice(-30).map((p) => ({ ...p, day: p.date.slice(5) })), [trend.data])
  const monthly = useMemo(() => {
    const months = new Map<string, { present: number; absent: number }>()
    for (const p of trend.data ?? []) {
      const m = months.get(p.date.slice(0, 7)) ?? { present: 0, absent: 0 }
      m.present += p.present
      m.absent += p.absent
      months.set(p.date.slice(0, 7), m)
    }
    return [...months].map(([month, m]) => ({
      month,
      rate: m.present + m.absent ? Math.round((1000 * m.present) / (m.present + m.absent)) / 10 : 0,
    }))
  }, [trend.data])

  const s = overview.data?.summary
  const cards: { label: string; value?: number; color: string; to?: string }[] = [
    { label: 'Employees', value: s?.total_employees, color: 'text.primary', to: '/attendance' },
    { label: 'Present', value: s?.present, color: 'success.main', to: '/attendance' },
    { label: 'Late', value: s?.late, color: 'warning.main', to: '/attendance' },
    { label: 'Absent', value: s?.absent, color: 'error.main', to: '/attendance' },
    { label: 'Checked in now', value: s?.checked_in_now, color: 'success.main', to: '/attendance' },
    { label: 'Missing check-out', value: s?.missing_checkout, color: 'error.main', to: '/attendance' },
    { label: 'Suspicious attempts', value: overview.data?.suspicious_attempts, color: 'secondary.main', to: '/review' },
    { label: 'Rejected attempts', value: overview.data?.rejected_attempts, color: 'error.main', to: '/review' },
    { label: 'Waiting for review', value: overview.data?.pending_reviews_total, color: 'secondary.main', to: '/review' },
  ]

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} sx={{ alignItems: 'center' }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5" sx={{ fontWeight: 700 }}>Company overview</Typography>
          <Typography color="text.secondary">{longDate(date)}</Typography>
        </Box>
        <TextField type="date" size="small" label="Date" value={date}
          onChange={(e) => e.target.value && setDate(e.target.value)}
          slotProps={{ inputLabel: { shrink: true }, htmlInput: { max: todayIso() } }} />
      </Stack>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))' }}>
        {cards.map((c) => (
          <Card key={c.label} variant="outlined">
            <CardActionArea onClick={() => c.to && navigate(c.to)}>
              <CardContent>
                <Typography variant="h4" sx={{ color: c.color, fontWeight: 700 }}>{c.value ?? '–'}</Typography>
                <Typography color="text.secondary">{c.label}</Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        ))}
      </Box>

      <Box sx={{ display: 'grid', gap: 2, gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' } }}>
        <ChartCard title="Attendance by location">
          <ResponsiveContainer>
            <BarChart data={overview.data?.by_location ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="present" name="Present" stackId="a" fill={COLORS.present} />
              <Bar dataKey="pending_review" name="Pending review" stackId="a" fill={COLORS.pending} />
              <Bar dataKey="absent" name="Absent" stackId="a" fill={COLORS.absent} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Attendance by department">
          <ResponsiveContainer>
            <BarChart data={overview.data?.by_department ?? []}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="present" name="Present" stackId="a" fill={COLORS.present} />
              <Bar dataKey="pending_review" name="Pending review" stackId="a" fill={COLORS.pending} />
              <Bar dataKey="absent" name="Absent" stackId="a" fill={COLORS.absent} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Late arrivals and absences – last 30 days">
          <ResponsiveContainer>
            <LineChart data={last30}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="day" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Line type="monotone" dataKey="present" name="Present" stroke={COLORS.present} dot={false} />
              <Line type="monotone" dataKey="late" name="Late" stroke={COLORS.late} dot={false} />
              <Line type="monotone" dataKey="absent" name="Absent" stroke={COLORS.absent} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Monthly attendance rate (%)">
          <ResponsiveContainer>
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="month" />
              <YAxis domain={[0, 100]} />
              <Tooltip />
              <Bar dataKey="rate" name="Attendance %" fill="#1F5FAD" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </Box>
    </Stack>
  )
}
