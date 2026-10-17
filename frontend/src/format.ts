const amountFormat = new Intl.NumberFormat('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const dateFormat = new Intl.DateTimeFormat('en-IN', { day: '2-digit', month: 'short', year: 'numeric' })

/** "85000.00" -> "85,000.00"; zero or missing -> "" so empty debit/credit cells stay blank. */
export function formatAmount(value: string | null): string {
  if (value === null) return ''
  const number = Number(value)
  return number === 0 ? '' : amountFormat.format(number)
}

/** "2024-04-01" -> "01 Apr 2024" (parsed as a calendar date, not shifted by time zone). */
export function formatDate(value: string): string {
  const [year, month, day] = value.split('-').map(Number)
  return dateFormat.format(new Date(year, month - 1, day))
}

/** "923010012345678" -> "•••• 5678". */
export function maskAccount(value: string | null): string {
  if (!value) return '—'
  return value.length > 4 ? `•••• ${value.slice(-4)}` : value
}
