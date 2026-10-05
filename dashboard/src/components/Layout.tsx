import BadgeIcon from '@mui/icons-material/Badge'
import BusinessIcon from '@mui/icons-material/Business'
import DashboardIcon from '@mui/icons-material/Dashboard'
import EventIcon from '@mui/icons-material/Event'
import FingerprintIcon from '@mui/icons-material/Fingerprint'
import GppMaybeIcon from '@mui/icons-material/GppMaybe'
import HistoryIcon from '@mui/icons-material/History'
import SecurityIcon from '@mui/icons-material/Security'
import ScheduleIcon from '@mui/icons-material/Schedule'
import PeopleIcon from '@mui/icons-material/People'
import PhoneAndroidIcon from '@mui/icons-material/PhoneAndroid'
import QrCode2Icon from '@mui/icons-material/QrCode2'
import AssessmentIcon from '@mui/icons-material/Assessment'
import SettingsIcon from '@mui/icons-material/Settings'
import TableChartIcon from '@mui/icons-material/TableChart'
import AppBar from '@mui/material/AppBar'
import Badge from '@mui/material/Badge'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Drawer from '@mui/material/Drawer'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemIcon from '@mui/material/ListItemIcon'
import ListItemText from '@mui/material/ListItemText'
import Menu from '@mui/material/Menu'
import MenuItem from '@mui/material/MenuItem'
import Toolbar from '@mui/material/Toolbar'
import Typography from '@mui/material/Typography'
import { useQuery } from '@tanstack/react-query'
import { useState, type ReactNode } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

import { apiGet } from '../api/client'
import type { Page, ReviewItem } from '../api/hrTypes'
import { useAuth, useCurrentUser } from '../auth/AuthProvider'
import { NotificationBell } from './NotificationBell'

const DRAWER_WIDTH = 230

type NavItem = { to: string; label: string; icon: ReactNode; badge?: number }

export function Layout({ children }: { children: ReactNode }) {
  const user = useCurrentUser()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const [menu, setMenu] = useState<HTMLElement | null>(null)
  const isHr = user.role === 'HR' || user.role === 'ADMIN'

  // Things waiting for HR: flagged attendance and new phones.
  const pendingReviews = useQuery({
    queryKey: ['badge-review'],
    queryFn: () => apiGet<Page<ReviewItem>>('/hr/review', { state: 'PENDING', limit: '1' }),
    enabled: isHr,
    refetchInterval: 60_000,
  })
  const pendingPhones = useQuery({
    queryKey: ['badge-phones'],
    queryFn: () => apiGet<{ total: number }>('/devices', { status: 'PENDING_APPROVAL', page_size: '1' }),
    enabled: isHr,
    refetchInterval: 60_000,
  })
  const openAlerts = useQuery({
    queryKey: ['badge-alerts'],
    queryFn: () => apiGet<{ total: number }>('/security/alerts', { status: 'active', limit: '1' }),
    enabled: isHr,
    refetchInterval: 60_000,
  })
  const reviews = pendingReviews.data?.total ?? 0
  const phones = pendingPhones.data?.total ?? 0

  const nav: NavItem[] = isHr
    ? [
        { to: '/', label: 'Dashboard', icon: <DashboardIcon /> },
        { to: '/attendance', label: 'Attendance', icon: <TableChartIcon /> },
        { to: '/review', label: 'Suspicious activity', icon: <GppMaybeIcon />, badge: reviews },
        { to: '/employees', label: 'Employees', icon: <PeopleIcon /> },
        { to: '/organization', label: 'Locations & departments', icon: <BusinessIcon /> },
        { to: '/phones', label: 'Phones', icon: <PhoneAndroidIcon />, badge: phones },
        { to: '/qr-screens', label: 'QR screens', icon: <QrCode2Icon /> },
        { to: '/calendar', label: 'Holidays & leave', icon: <EventIcon /> },
        { to: '/reports', label: 'Reports', icon: <AssessmentIcon /> },
        { to: '/scheduled-reports', label: 'Scheduled reports', icon: <ScheduleIcon /> },
        { to: '/security', label: 'Security monitoring', icon: <SecurityIcon />, badge: openAlerts.data?.total ?? 0 },
        { to: '/audit-log', label: 'Audit log', icon: <HistoryIcon /> },
        { to: '/settings', label: 'Security settings', icon: <SettingsIcon /> },
      ]
    : [
        { to: '/', label: 'My team', icon: <BadgeIcon /> },
        { to: '/reports', label: 'Reports', icon: <AssessmentIcon /> },
      ]

  return (
    <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'grey.50' }}>
      <AppBar position="fixed" sx={{ zIndex: (t) => t.zIndex.drawer + 1 }}>
        <Toolbar>
          <FingerprintIcon sx={{ mr: 1 }} />
          <Typography variant="h6" sx={{ flexGrow: 1 }}>Attendance</Typography>
          <NotificationBell />
          <Button color="inherit" onClick={(e) => setMenu(e.currentTarget)}>
            {user.employee?.full_name ?? user.email} · {user.role}
          </Button>
          <Menu anchorEl={menu} open={Boolean(menu)} onClose={() => setMenu(null)}>
            <MenuItem onClick={() => { setMenu(null); navigate('/change-password') }}>Change password</MenuItem>
            <MenuItem onClick={() => { setMenu(null); logout() }}>Log out</MenuItem>
          </Menu>
        </Toolbar>
      </AppBar>
      <Drawer
        variant="permanent"
        sx={{ width: DRAWER_WIDTH, flexShrink: 0, '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' } }}
      >
        <Toolbar />
        <List>
          {nav.map((item) => (
            <ListItemButton key={item.to} component={NavLink} to={item.to} end
              sx={{ '&.active': { bgcolor: 'action.selected' } }}>
              <ListItemIcon>
                <Badge badgeContent={item.badge} color="error">{item.icon}</Badge>
              </ListItemIcon>
              <ListItemText primary={item.label} />
            </ListItemButton>
          ))}
        </List>
      </Drawer>
      <Box component="main" sx={{ flexGrow: 1, p: 3, minWidth: 0 }}>
        <Toolbar />
        {children}
      </Box>
    </Box>
  )
}
