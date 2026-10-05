/** "2026-10-05T08:07:00Z" -> "09:07" in the company's timezone. */
export function formatTime(iso: string | null, timeZone = 'Africa/Lagos'): string {
  if (!iso) return '—'
  return new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', timeZone }).format(new Date(iso))
}

export function formatMinutes(minutes: number): string {
  if (!minutes) return '—'
  return `${Math.floor(minutes / 60)}h ${String(minutes % 60).padStart(2, '0')}m`
}

/** Today's date (YYYY-MM-DD) in the company's timezone. */
export function todayIso(timeZone = 'Africa/Lagos'): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone }).format(new Date())
}

export function longDate(iso: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC',
  }).format(new Date(`${iso}T00:00:00Z`))
}
