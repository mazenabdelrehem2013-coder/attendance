import NotificationsIcon from '@mui/icons-material/Notifications'
import Badge from '@mui/material/Badge'
import Box from '@mui/material/Box'
import Button from '@mui/material/Button'
import Divider from '@mui/material/Divider'
import IconButton from '@mui/material/IconButton'
import List from '@mui/material/List'
import ListItemButton from '@mui/material/ListItemButton'
import ListItemText from '@mui/material/ListItemText'
import Popover from '@mui/material/Popover'
import Stack from '@mui/material/Stack'
import Tooltip from '@mui/material/Tooltip'
import Typography from '@mui/material/Typography'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { apiGet, apiPost } from '../api/client'
import type { NotificationItem, NotificationList } from '../api/scheduleTypes'

function ago(iso: string): string {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  if (minutes < 24 * 60) return `${Math.round(minutes / 60)} h ago`
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })
}

/** Bell in the top bar: the user's own alerts (late arrivals, check-ins to review, new phones…). */
export function NotificationBell() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [anchor, setAnchor] = useState<HTMLElement | null>(null)
  const list = useQuery({
    queryKey: ['notifications'],
    queryFn: () => apiGet<NotificationList>('/notifications', { limit: '30' }),
    refetchInterval: 60_000,
  })
  const unread = list.data?.unread ?? 0
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['notifications'] })

  async function open(item: NotificationItem) {
    setAnchor(null)
    if (!item.read) await apiPost(`/notifications/${item.id}/read`).catch(() => undefined)
    refresh()
    if (item.link) navigate(item.link)
  }

  async function readAll() {
    await apiPost('/notifications/read-all')
    refresh()
  }

  return (
    <>
      <Tooltip title={unread ? `${unread} new alert${unread === 1 ? '' : 's'}` : 'Alerts'}>
        <IconButton color="inherit" aria-label="Alerts" onClick={(e) => setAnchor(e.currentTarget)}>
          <Badge badgeContent={unread} color="error"><NotificationsIcon /></Badge>
        </IconButton>
      </Tooltip>
      <Popover open={Boolean(anchor)} anchorEl={anchor} onClose={() => setAnchor(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }} transformOrigin={{ vertical: 'top', horizontal: 'right' }}>
        <Box sx={{ width: 380, maxHeight: 480, display: 'flex', flexDirection: 'column' }}>
          <Stack direction="row" sx={{ alignItems: 'center', px: 2, py: 1 }}>
            <Typography sx={{ fontWeight: 600, flexGrow: 1 }}>Alerts</Typography>
            <Button size="small" disabled={!unread} onClick={readAll}>Mark all as read</Button>
          </Stack>
          <Divider />
          {list.data?.items.length ? (
            <List dense sx={{ overflowY: 'auto' }}>
              {list.data.items.map((n) => (
                <ListItemButton key={n.id} onClick={() => open(n)}
                  sx={{ alignItems: 'flex-start', bgcolor: n.read ? undefined : 'action.hover' }}>
                  <ListItemText
                    primary={n.title}
                    secondary={`${ago(n.created_at)} · ${n.body}`}
                    slotProps={{
                      primary: { sx: { fontWeight: n.read ? 400 : 600 } },
                      secondary: { sx: { display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' } },
                    }}
                  />
                </ListItemButton>
              ))}
            </List>
          ) : (
            <Typography color="text.secondary" sx={{ p: 3, textAlign: 'center' }}>No alerts.</Typography>
          )}
        </Box>
      </Popover>
    </>
  )
}
