import Alert from '@mui/material/Alert'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import CircularProgress from '@mui/material/CircularProgress'
import { Navigate, Route, Routes, useLocation } from 'react-router-dom'

import { useAuth } from './auth/AuthProvider'
import { Layout } from './components/Layout'
import { ChangePasswordPage } from './pages/ChangePasswordPage'
import { DashboardPage } from './pages/DashboardPage'
import { CalendarPage } from './pages/hr/CalendarPage'
import { EmployeesPage } from './pages/hr/EmployeesPage'
import { HrOverviewPage } from './pages/hr/HrOverviewPage'
import { OrganizationPage } from './pages/hr/OrganizationPage'
import { PhonesPage } from './pages/hr/PhonesPage'
import { QrScreensPage } from './pages/hr/QrScreensPage'
import { ReviewPage } from './pages/hr/ReviewPage'
import { AuditLogPage } from './pages/hr/AuditLogPage'
import { ScheduledReportsPage } from './pages/hr/ScheduledReportsPage'
import { SecurityPage } from './pages/hr/SecurityPage'
import { SettingsPage } from './pages/hr/SettingsPage'
import { LoginPage } from './pages/LoginPage'
import { QrDisplayPage } from './pages/QrDisplayPage'
import { ReportsPage } from './pages/ReportsPage'

export default function App() {
  const { state, logout } = useAuth()
  const location = useLocation()

  // The office QR screen has no user login (it uses its own screen key).
  if (location.pathname === '/qr-display') return <QrDisplayPage />

  if (state.status === 'checking') {
    return <Box sx={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}><CircularProgress /></Box>
  }
  if (state.status === 'loggedOut') return <LoginPage notice={state.notice} />
  if (state.user.must_change_password) return <ChangePasswordPage forced />
  if (state.user.role === 'EMPLOYEE') {
    return (
      <Box sx={{ maxWidth: 480, mx: 'auto', mt: 10 }}>
        <Alert severity="info" action={<Button onClick={logout}>Log out</Button>}>
          The dashboard is for managers, HR and administrators. Please use the mobile app to record your attendance.
        </Alert>
      </Box>
    )
  }
  const isHr = state.user.role === 'HR' || state.user.role === 'ADMIN'
  return (
    <Layout>
      <Routes>
        <Route path="/" element={isHr ? <HrOverviewPage /> : <DashboardPage />} />
        <Route path="/change-password" element={<ChangePasswordPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        {isHr && (
          <>
            <Route path="/attendance" element={<DashboardPage />} />
            <Route path="/review" element={<ReviewPage />} />
            <Route path="/employees" element={<EmployeesPage />} />
            <Route path="/organization" element={<OrganizationPage />} />
            <Route path="/phones" element={<PhonesPage />} />
            <Route path="/qr-screens" element={<QrScreensPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/scheduled-reports" element={<ScheduledReportsPage />} />
            <Route path="/security" element={<SecurityPage />} />
            <Route path="/audit-log" element={<AuditLogPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </>
        )}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  )
}
